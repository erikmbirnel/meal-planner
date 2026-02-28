import json
import re
from typing import Optional

import anthropic

from app.models import Ingredient, Meal

_SYSTEM_PROMPT = """\
You are a helpful meal planning assistant. When asked to generate meals or parse \
ingredients, always respond with valid JSON and nothing else.
"""


def _extract_json(text: str) -> str:
    """Strip markdown code fences if Claude wraps the response in them."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ``` wrappers
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    return text


class ClaudeClient:
    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = "claude-sonnet-4-6"

    def generate_meal_ideas(
        self,
        existing_meals: list[Meal],
        cuisine: Optional[str] = None,
        constraints: Optional[str] = None,
        exclude_ingredients: list[str] = [],
        count: int = 3,
    ) -> list[Meal]:
        existing_names = [m.name for m in existing_meals]
        prompt_parts = [
            f"Generate {count} dinner meal idea(s) with full ingredient lists.",
        ]
        if cuisine:
            prompt_parts.append(f"Cuisine: {cuisine}.")
        if constraints:
            prompt_parts.append(f"Constraints: {constraints}.")
        if exclude_ingredients:
            prompt_parts.append(
                f"Exclude these ingredients: {', '.join(exclude_ingredients)}."
            )
        if existing_names:
            prompt_parts.append(
                f"Do not repeat these existing meals: {', '.join(existing_names[:30])}."
            )

        prompt_parts.append(
            """
Return a JSON array of meal objects. Each object must have:
- name (string)
- servings (int, default 4)
- cuisine (string, e.g. "Italian", "Mexican", "Asian", "American", "Mediterranean")
- staple (bool, true if it's a quick weeknight staple)
- ingredients: array of {name, quantity, unit} objects
  - unit can be: "can", "lb", "oz", "cup", "cups", "tbsp", "tsp", "clove", "cloves", "bunch", "stalk", "stalks", or "" for whole items

Example:
[
  {
    "name": "Chickpea Tacos",
    "servings": 4,
    "cuisine": "Mexican",
    "staple": true,
    "ingredients": [
      {"name": "chickpeas", "quantity": 1, "unit": "can"},
      {"name": "corn tortillas", "quantity": 8, "unit": ""},
      {"name": "lime", "quantity": 1, "unit": ""},
      {"name": "cumin", "quantity": 1, "unit": "tsp"}
    ]
  }
]
"""
        )

        message = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": " ".join(prompt_parts)}],
        )

        raw = _extract_json(message.content[0].text)
        data = json.loads(raw)
        meals = []
        for i, item in enumerate(data):
            ingredients = [Ingredient(**ing) for ing in item["ingredients"]]
            meal = Meal(
                id=-(i + 1),  # Temporary negative IDs for generated meals
                name=item["name"],
                servings=item.get("servings", 4),
                cuisine=item.get("cuisine", ""),
                staple=bool(item.get("staple", False)),
                ingredients=ingredients,
            )
            meals.append(meal)
        return meals

    def generate_meal_with_recipe(self, title: str, user_notes: str = "") -> dict:
        """Generate a full meal record + recipe for a given title.

        Returns {"meal": Meal, "instructions": str}.
        """
        prompt = (
            f"Create a complete meal record and recipe for: {title}\n\n"
            "Return a JSON object with:\n"
            '- name (string)\n'
            '- servings (int, default 4)\n'
            '- cuisine (string, e.g. "Italian", "Mexican", "Asian", "American", "Mediterranean", "Indian")\n'
            '- staple (bool, true if it\'s a quick weeknight staple)\n'
            '- ingredients: array of {name, quantity, unit} objects\n'
            '  - unit can be: "can", "lb", "oz", "cup", "cups", "tbsp", "tsp", "clove", "cloves", "bunch", "stalk", "stalks", or "" for whole items\n'
            '- instructions (string, numbered cooking steps, concise and practical)\n\n'
            'Example:\n'
            '{\n'
            '  "name": "Chicken Tikka Masala",\n'
            '  "servings": 4,\n'
            '  "cuisine": "Indian",\n'
            '  "staple": false,\n'
            '  "ingredients": [\n'
            '    {"name": "chicken breast", "quantity": 1.5, "unit": "lb"},\n'
            '    {"name": "tomato sauce", "quantity": 1, "unit": "can"}\n'
            '  ],\n'
            '  "instructions": "1. Marinate chicken...\\n2. Cook sauce..."\n'
            '}'
        )
        if user_notes:
            prompt += f"\n\nNotes from the cook:\n{user_notes}"
        message = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _extract_json(message.content[0].text)
        data = json.loads(raw)
        ingredients = [Ingredient(**ing) for ing in data.get("ingredients", [])]
        meal = Meal(
            id=0,
            name=data.get("name", title),
            servings=int(data.get("servings", 4)),
            cuisine=data.get("cuisine", ""),
            staple=bool(data.get("staple", False)),
            ingredients=ingredients,
        )
        return {"meal": meal, "instructions": data["instructions"]}

    def generate_recipe(self, meal: Meal, user_notes: str = "") -> str:
        ing_lines = "\n".join(
            f"- {i.quantity} {i.unit} {i.name}".strip()
            for i in meal.ingredients
        )
        prompt = (
            f"Write simple, clear step-by-step cooking instructions for {meal.name} "
            f"(serves {meal.servings}).\n\n"
            f"Ingredients:\n{ing_lines}\n"
        )
        if user_notes:
            prompt += f"\nNotes from the cook:\n{user_notes}\n"
        prompt += "\nFormat as numbered steps. Be concise and practical. No intro or outro."

        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    def parse_ingredients(self, raw_text: str) -> list[Ingredient]:
        prompt = f"""Parse the following ingredient list into structured JSON.

Input:
{raw_text}

Return a JSON array of ingredient objects, each with:
- name (string, lowercase)
- quantity (number)
- unit (string: "can", "lb", "oz", "cup", "cups", "tbsp", "tsp", "clove", "cloves", \
"bunch", "stalk", "stalks", or "" for whole items like "1 onion")

Example: [{{"name": "garlic", "quantity": 3, "unit": "cloves"}}, \
{{"name": "onion", "quantity": 1, "unit": ""}}]

Return only the JSON array, no explanation."""

        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = _extract_json(message.content[0].text)
        data = json.loads(raw)
        return [Ingredient(**item) for item in data]
