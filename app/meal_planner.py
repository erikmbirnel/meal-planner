import random
from collections import Counter
from datetime import datetime, date, timedelta
from typing import Optional

from app.models import Ingredient, Meal, WeekPlan, IngredientMapping, DAYS
from app.sheets import SheetsClient
from app.todoist_client import TodoistClient
from app.claude_client import ClaudeClient


def _monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


class MealPlanner:
    def __init__(
        self,
        sheets: SheetsClient,
        todoist: TodoistClient,
        claude: ClaudeClient,
    ):
        self._sheets = sheets
        self._todoist = todoist
        self._claude = claude

    # ------------------------------------------------------------------
    # Plan generation
    # ------------------------------------------------------------------

    def generate_week_plan(self) -> WeekPlan:
        all_meals = self._sheets.get_all_meals()
        last_plan = self._sheets.get_last_week_plan()

        last_week_ids: set[int] = set()
        if last_plan:
            last_week_ids = set(last_plan.meals.values())

        selected_ids = self._select_meals(all_meals, last_week_ids)

        week_start = _monday_of_week(date.today())
        plan = WeekPlan(
            week_start=week_start,
            meals={day: meal_id for day, meal_id in zip(DAYS, selected_ids)},
            status="draft",
            created_at=datetime.now(),
        )
        self._sheets.save_week_plan(plan)
        return plan

    def _select_meals(
        self,
        all_meals: list[Meal],
        last_week_ids: set[int],
        count: int = 7,
    ) -> list[int]:
        if not all_meals:
            raise ValueError("No meals in library. Use /add to add meals first.")

        if len(all_meals) < count:
            # Not enough meals — repeat as needed
            ids = [m.id for m in all_meals]
            while len(ids) < count:
                ids.extend([m.id for m in all_meals])
            return ids[:count]

        # Prefer meals not in last week; allow max 1 repeat
        fresh = [m for m in all_meals if m.id not in last_week_ids]
        repeated = [m for m in all_meals if m.id in last_week_ids]

        if len(fresh) >= count:
            pool = fresh
        else:
            # Fill with up to 1 repeat
            pool = fresh + repeated[:1]

        # Ensure at least 1 staple
        staples = [m for m in pool if m.staple]
        non_staples = [m for m in pool if not m.staple]

        selected: list[Meal] = []
        if staples:
            selected.append(random.choice(staples))

        remaining_pool = [m for m in pool if m not in selected]
        random.shuffle(remaining_pool)

        # Fill remaining slots while maximising cuisine variety
        for meal in remaining_pool:
            if len(selected) >= count:
                break
            cuisines_so_far = Counter(m.cuisine for m in selected)
            # Allow a cuisine to repeat only if we have no other choice
            if cuisines_so_far.get(meal.cuisine, 0) < 2 or len(remaining_pool) <= count - len(selected):
                selected.append(meal)

        # If still short, append whatever is available
        if len(selected) < count:
            extra = [m for m in pool if m not in selected]
            random.shuffle(extra)
            selected.extend(extra[: count - len(selected)])

        random.shuffle(selected)
        return [m.id for m in selected[:count]]

    # ------------------------------------------------------------------
    # Plan editing
    # ------------------------------------------------------------------

    def swap_days(self, plan: WeekPlan, day1: str, day2: str) -> WeekPlan:
        meals = dict(plan.meals)
        meals[day1], meals[day2] = meals[day2], meals[day1]
        updated = plan.model_copy(update={"meals": meals})
        self._sheets.save_week_plan(updated)
        return updated

    def replace_meal(self, plan: WeekPlan, day: str, new_meal_id: int) -> WeekPlan:
        meals = dict(plan.meals)
        meals[day] = new_meal_id
        updated = plan.model_copy(update={"meals": meals})
        self._sheets.save_week_plan(updated)
        return updated

    # ------------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------------

    def confirm_plan(self, plan: WeekPlan) -> dict:
        # Load all meals for the plan
        meal_ids = list(plan.meals.values())
        meals_by_id: dict[int, Meal] = {}
        for mid in set(meal_ids):
            meal = self._sheets.get_meal_by_id(mid)
            if meal:
                meals_by_id[mid] = meal

        # Aggregate ingredients
        aggregated = self._aggregate_ingredients(
            [meals_by_id[mid] for mid in meal_ids if mid in meals_by_id]
        )

        # Get mappings and sync to Todoist
        mappings = self._sheets.get_ingredient_mappings()
        sync_result = self._todoist.sync_shopping_list(aggregated, mappings)

        # Mark plan as confirmed
        confirmed = plan.model_copy(
            update={"status": "confirmed", "confirmed_at": datetime.now()}
        )
        self._sheets.save_week_plan(confirmed)

        return {"plan": confirmed, "shopping": sync_result, "ingredients": aggregated}

    # ------------------------------------------------------------------
    # Meal options
    # ------------------------------------------------------------------

    def get_meal_options(self, exclude_ids: list[int] = []) -> list[Meal]:
        all_meals = self._sheets.get_all_meals()
        return [m for m in all_meals if m.id not in exclude_ids]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_ingredients(meals: list[Meal]) -> list[Ingredient]:
        totals: dict[tuple[str, str], float] = {}
        for meal in meals:
            for ing in meal.ingredients:
                key = (ing.name.lower(), ing.unit)
                totals[key] = totals.get(key, 0) + ing.quantity

        return [
            Ingredient(name=name, quantity=qty, unit=unit)
            for (name, unit), qty in sorted(totals.items())
        ]
