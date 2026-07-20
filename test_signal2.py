from app import signal_2_stylometry

clearly_ai = "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment."

clearly_human = "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there"

borderline_formal_human = "The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations."

borderline_edited_ai = "I've been thinking a lot about remote work lately. There are genuine tradeoffs — flexibility and no commute on one side, isolation and blurred work-life boundaries on the other. Studies show productivity varies widely by individual and role type."

print("Clearly AI:              ", signal_2_stylometry(clearly_ai))
print("Clearly human:           ", signal_2_stylometry(clearly_human))
print("Borderline formal human: ", signal_2_stylometry(borderline_formal_human))
print("Borderline edited AI:    ", signal_2_stylometry(borderline_edited_ai))   