from app import signal_1_llm_judge

human_text = "The sun dipped below the horizon, painting the sky in hues of amber and rose. I sat on the porch, coffee in hand, watching the neighborhood slowly go quiet."

ai_text = "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment."

print("Human-sounding text score:", signal_1_llm_judge(human_text))
print("AI-sounding text score:", signal_1_llm_judge(ai_text))