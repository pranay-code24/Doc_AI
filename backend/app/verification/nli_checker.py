import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.config import NLI_MODEL_NAME


class NLIChecker:
    def __init__(self, model_name: str = NLI_MODEL_NAME):
        print(f"Loading NLI verification model: {model_name} ...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.eval()

        # Labels dynamically read karo (hardcode mat karo)
        self.id2label = {
            int(k): v.lower() for k, v in self.model.config.id2label.items()
        }

    def predict(self, premise: str, hypothesis: str) -> dict[str, float]:
        """
        Check karta hai ki premise -> hypothesis ka relationship kya hai:
        returns {'entailment': float, 'neutral': float, 'contradiction': float}
        """
        inputs = self.tokenizer(
            premise,
            hypothesis,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = self.model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0].tolist()

        scores = {self.id2label[i]: round(float(p), 4) for i, p in enumerate(probs)}
        return {
            "entailment": scores.get("entailment", 0.0),
            "neutral": scores.get("neutral", 0.0),
            "contradiction": scores.get("contradiction", 0.0),
        }

    def is_entailed(
        self,
        quote: str,
        claim: str,
        min_entailment: float = 0.55,
        max_contradiction: float = 0.25,
    ) -> tuple[bool, dict[str, float]]:
        """
        Verify karta hai ki source quote claim ko support karta hai aur contradict nahi karta.
        """
        scores = self.predict(premise=quote, hypothesis=claim)
        passed = (
            scores["entailment"] >= min_entailment
            and scores["contradiction"] <= max_contradiction
        )
        return passed, scores