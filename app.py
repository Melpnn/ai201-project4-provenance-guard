import os
import uuid
import json
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from groq import Groq

# Load the GROQ_API_KEY from your .env file into the environment
load_dotenv()

app = Flask(__name__)
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


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "text and creator_id are required"}), 400

    content_id = str(uuid.uuid4())
    signal1_score = signal_1_llm_judge(text)

    # attribution is a simple real read on signal 1 alone, for now
    if signal1_score >= 0.65:
        attribution = "likely_ai"
    elif signal1_score >= 0.40:
        attribution = "uncertain"
    else:
        attribution = "likely_human"

    # Confidence/label stay as placeholders until Milestone 4 adds Signal 2 + real combined scoring
    confidence = signal1_score
    label = "placeholder label"

    log_entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": signal1_score,
        "status": "classified"
    }
    append_to_log(log_entry)

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "signal1_score": signal1_score
    })


@app.route("/log", methods=["GET"])
def log():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(debug=True, port=5000)