# Fixtures (self-authored)

`interview-fr-tts.wav` — a 2-voice French mini-interview synthesized with macOS `say` (voices
"Flo (French (France))" as interviewer A and "Jacques" as interviewee B), 16 kHz mono, created
2026-10-11 for flexasr's smoke test. Our own material: free to use and publish.

Script (A / B alternate, 0.6 s silence between turns):
- A: Bonjour. Vous habitez ici depuis longtemps ?
- B: Euh, oui. Je je suis né ici, en fait. Mon père travaillait au port.
- A: Et qu'est-ce qui a changé dans le quartier ?
- B: Beaucoup de choses. Les magasins, surtout. Avant, il y avait une boulangerie à chaque coin de rue.

Synthetic speech is clean read speech: good for testing the pipeline, not for judging models
(use the gold sample of real interviews for that).
