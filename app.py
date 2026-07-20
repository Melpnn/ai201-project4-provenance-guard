import os
import uuid
import json
import re
import statistics
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from groq import Groq
# Load the GROQ_API_KEY from your .env file into the environment
load_dotenv()

app = Flask(__name__)

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

LOG_FILE = "audit_log.json"


def get_log():
    """Reads the audit log file and returns a list of entries (empty list if file doesn't exist yet)."""
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r") as f:
        return json.load(f)


def append_to_log(entry):
    """Appends one new entry to the audit log file."""
    entries = get_log()
    entries.append(entry)
    with open(LOG_FILE, "w") as f:
        json.dump(entries, f, indent=2)

def update_log_entry(content_id, updates):
    """
    Finds the log entry matching content_id and updates it with the given
    fields (a dict). Returns True if found and updated, False if not found.
    """
    entries = get_log()
    for entry in entries:
        if entry["content_id"] == content_id:
            entry.update(updates)
            with open(LOG_FILE, "w") as f:
                json.dump(entries, f, indent=2)
            return True
    return False

def signal_1_llm_judge(text):
    """
    Sends the text to an LLM and asks it to rate, 0-1, how likely
    the text is to be AI-generated. Returns a float between 0 and 1.
    """
    prompt = f"""You are a text-origin classifier. Read the following text and
estimate how likely it is that the text was written by an AI rather than a human.

Scoring scale (make sure your final score matches your reasoning):
- 0.0-0.2 = clearly human: casual, irregular, personal voice
- 0.4-0.6 = mixed or unclear signals
- 0.8-1.0 = clearly AI: formal, hedge-heavy, generic phrasing like
  "it is important to note", "furthermore", "paradigm shift"

Respond ONLY with a JSON object in this exact format, nothing else.
Write your reasoning FIRST, then assign a score that matches that reasoning:
{{"reasoning": "<one sentence explanation>", "score": <float between 0 and 1>}}

Text to evaluate:
\"\"\"{text}\"\"\"
"""

    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    raw_output = response.choices[0].message.content.strip()

    try:
        parsed = json.loads(raw_output)
        score = float(parsed["score"])
        # clamp in case the model returns something out of range
        score = max(0.0, min(1.0, score))
        return score
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"Signal 1 parsing error: {e}. Raw output: {raw_output}")
        # fallback: return a neutral score rather than crashing
        return 0.5

def signal_2_stylometry(text):
    """
    Computes sentence-length variability (coefficient of variation) and
    type-token ratio (unique words / total words). Returns a float between
    0 and 1, where higher = more "AI-like" (low variability, low lexical variety).
    """
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    words = re.findall(r"\b[\w']+\b", text.lower())

    if len(sentences) < 2 or len(words) < 5:
        # Not enough text to compute meaningful stats — return neutral score
        return 0.5

    # --- Sentence length variability (coefficient of variation) ---
    sentence_lengths = [len(re.findall(r"\b[\w']+\b", s)) for s in sentences]
    mean_len = statistics.mean(sentence_lengths)
    stdev_len = statistics.stdev(sentence_lengths)

    if mean_len == 0:
        return 0.5

    # CV = stdev / mean — measures variability RELATIVE to average sentence
    # length, so one long or short outlier sentence doesn't distort things
    # the way raw variance does.
    cv = stdev_len / mean_len
    # Normalize: CV of ~0.6+ is quite variable (human-like); clamp at 1.0
    normalized_cv = max(0.0, min(1.0, cv / 0.6))
    variance_score = 1.0 - normalized_cv  # low variability -> high AI score

    # --- Type-token ratio ---
    ttr = len(set(words)) / len(words)
    ttr_score = 1.0 - ttr  # low variety -> high AI score

    combined = (variance_score + ttr_score) / 2
    return max(0.0, min(1.0, combined))

def compute_confidence(signal1_score, signal2_score):
    """
    Combines Signal 1 and Signal 2 into one confidence score using the
    weighted formula from planning.md: Signal 1 is weighted higher (0.7)
    because it reads the whole text holistically; Signal 2 (0.3) is a
    narrower statistical check.
    """
    return (0.7 * signal1_score) + (0.3 * signal2_score)


def get_label(confidence):
    """
    Maps a confidence score to one of the three transparency label variants,
    using the thresholds from planning.md (0.40 / 0.65).
    """
    if confidence >= 0.65:
        return f"This content is likely AI-generated. (Confidence: {confidence:.2f})"
    elif confidence >= 0.40:
        return f"This content's origin is uncertain - our signals produced mixed results. (Confidence: {confidence:.2f})"
    else:
        return f"This content is likely human-written. (Confidence: {confidence:.2f})"


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json()
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "text and creator_id are required"}), 400

    content_id = str(uuid.uuid4())
    signal1_score = signal_1_llm_judge(text)
    signal2_score = signal_2_stylometry(text)

    confidence = compute_confidence(signal1_score, signal2_score)
    label = get_label(confidence)

    if confidence >= 0.65:
        attribution = "likely_ai"
    elif confidence >= 0.40:
        attribution = "uncertain"
    else:
        attribution = "likely_human"

    log_entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": signal1_score,
        "stylometry_score": signal2_score,
        "status": "classified"
    }
    append_to_log(log_entry)

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "signal1_score": signal1_score,
        "signal2_score": signal2_score
    })

@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json()
    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    if not content_id or not creator_reasoning:
        return jsonify({"error": "content_id and creator_reasoning are required"}), 400

    found = update_log_entry(content_id, {
        "status": "under_review",
        "appeal_reasoning": creator_reasoning
    })

    if not found:
        return jsonify({"error": "content_id not found"}), 404

    return jsonify({
        "content_id": content_id,
        "status": "under_review",
        "message": "Your appeal has been received and is under review."
    })

@app.route("/log", methods=["GET"])
def log():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(debug=True, port=5000)