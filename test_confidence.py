from app import signal_1_llm_judge, signal_2_stylometry, compute_confidence, get_label

clearly_ai = "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment."

clearly_human = "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there"

borderline_formal_human = "The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations."

borderline_edited_ai = "I've been thinking a lot about remote work lately. There are genuine tradeoffs — flexibility and no commute on one side, isolation and blurred work-life boundaries on the other. Studies show productivity varies widely by individual and role type."

test_cases = {
    "Clearly AI": clearly_ai,
    "Clearly human": clearly_human,
    "Borderline formal human": borderline_formal_human,
    "Borderline edited AI": borderline_edited_ai,
}

for name, text in test_cases.items():
    s1 = signal_1_llm_judge(text)
    s2 = signal_2_stylometry(text)
    conf = compute_confidence(s1, s2)
    label = get_label(conf)
    print(f"\n{name}")
    print(f"  signal1={s1:.2f}  signal2={s2:.2f}  confidence={conf:.2f}")
    print(f"  {label}")