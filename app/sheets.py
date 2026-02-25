import json
from datetime import datetime, date
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from app.models import Ingredient, IngredientMapping, Meal, WeekPlan, DAYS


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class SheetsClient:
    def __init__(
        self,
        spreadsheet_id: str,
        credentials_path: str = None,
        credentials_json: str = None,
    ):
        if credentials_json:
            info = json.loads(credentials_json)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        gc = gspread.authorize(creds)
        self._spreadsheet = gc.open_by_key(spreadsheet_id)
        self._meals_ws = self._spreadsheet.worksheet("meals")
        self._plans_ws = self._spreadsheet.worksheet("weekly_plans")
        self._mappings_ws = self._spreadsheet.worksheet("ingredient_mappings")
        self._recipes_ws = self._spreadsheet.worksheet("recipes")

    # ------------------------------------------------------------------
    # Meals
    # ------------------------------------------------------------------

    def get_all_meals(self) -> list[Meal]:
        records = self._meals_ws.get_all_records()
        meals = []
        for r in records:
            meals.append(self._row_to_meal(r))
        return meals

    def get_meal_by_id(self, meal_id: int) -> Optional[Meal]:
        records = self._meals_ws.get_all_records()
        for r in records:
            if int(r["id"]) == meal_id:
                return self._row_to_meal(r)
        return None

    def add_meal(self, meal: Meal) -> int:
        records = self._meals_ws.get_all_records()
        next_id = max((int(r["id"]) for r in records), default=0) + 1
        row = [
            next_id,
            meal.name,
            meal.servings,
            meal.cuisine,
            "TRUE" if meal.staple else "FALSE",
            json.dumps([i.model_dump() for i in meal.ingredients]),
        ]
        self._meals_ws.append_row(row, value_input_option="USER_ENTERED")
        return next_id

    def update_meal(self, meal: Meal) -> None:
        records = self._meals_ws.get_all_records()
        for idx, r in enumerate(records):
            if int(r["id"]) == meal.id:
                row_num = idx + 2  # 1-indexed + header
                self._meals_ws.update(
                    f"A{row_num}:F{row_num}",
                    [[
                        meal.id,
                        meal.name,
                        meal.servings,
                        meal.cuisine,
                        "TRUE" if meal.staple else "FALSE",
                        json.dumps([i.model_dump() for i in meal.ingredients]),
                    ]],
                    value_input_option="USER_ENTERED",
                )
                return

    # ------------------------------------------------------------------
    # Weekly plans
    # ------------------------------------------------------------------

    def get_last_week_plan(self) -> Optional[WeekPlan]:
        records = self._plans_ws.get_all_records()
        confirmed = [r for r in records if r.get("status") == "confirmed"]
        if not confirmed:
            return None
        latest = max(confirmed, key=lambda r: r["week_start"])
        return self._row_to_plan(latest)

    def get_draft_plan(self) -> Optional[WeekPlan]:
        records = self._plans_ws.get_all_records()
        drafts = [r for r in records if r.get("status") == "draft"]
        if not drafts:
            return None
        latest = max(drafts, key=lambda r: r["created_at"])
        return self._row_to_plan(latest)

    def save_week_plan(self, plan: WeekPlan) -> None:
        records = self._plans_ws.get_all_records()
        week_str = plan.week_start.isoformat()

        # Find existing row for this week (any status) and update in place.
        # Matching on week_start alone ensures a draft row is overwritten when
        # the plan is confirmed, rather than a second row being appended.
        for idx, r in enumerate(records):
            if r["week_start"] == week_str:
                row_num = idx + 2  # 1-indexed + header row
                self._plans_ws.update(
                    f"A{row_num}:K{row_num}",
                    [self._plan_to_row(plan)],
                    value_input_option="USER_ENTERED",
                )
                return

        # No existing row for this week — append
        self._plans_ws.append_row(
            self._plan_to_row(plan), value_input_option="USER_ENTERED"
        )

    # ------------------------------------------------------------------
    # Ingredient mappings
    # ------------------------------------------------------------------

    def get_ingredient_mappings(self) -> dict[str, IngredientMapping]:
        records = self._mappings_ws.get_all_records()
        mappings: dict[str, IngredientMapping] = {}
        for r in records:
            m = IngredientMapping(
                keyword=r["keyword"].lower(),
                todoist_section=r["todoist_section"],
                display_name=r["display_name"],
            )
            mappings[m.keyword] = m
        return mappings

    # ------------------------------------------------------------------
    # Recipes
    # ------------------------------------------------------------------

    def get_recipe(self, meal_id: int) -> Optional[dict]:
        records = self._recipes_ws.get_all_records()
        for r in records:
            if int(r["meal_id"]) == meal_id:
                return {
                    "instructions": r["instructions"],
                    "user_notes": r.get("user_notes", ""),
                    "generated_at": r.get("generated_at", ""),
                }
        return None

    def save_recipe(self, meal_id: int, instructions: str, user_notes: str = "") -> None:
        now = datetime.utcnow().isoformat()
        records = self._recipes_ws.get_all_records()
        for idx, r in enumerate(records):
            if int(r["meal_id"]) == meal_id:
                row_num = idx + 2
                self._recipes_ws.update(
                    f"A{row_num}:D{row_num}",
                    [[meal_id, instructions, user_notes, now]],
                    value_input_option="USER_ENTERED",
                )
                return
        self._recipes_ws.append_row(
            [meal_id, instructions, user_notes, now],
            value_input_option="USER_ENTERED",
        )

    def add_ingredient_mapping(self, mapping: IngredientMapping) -> None:
        self._mappings_ws.append_row(
            [mapping.keyword, mapping.todoist_section, mapping.display_name],
            value_input_option="USER_ENTERED",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_meal(r: dict) -> Meal:
        raw = r["ingredients"]
        if isinstance(raw, str):
            ingredients_data = json.loads(raw)
        else:
            ingredients_data = raw or []
        ingredients = [Ingredient(**i) for i in ingredients_data]
        return Meal(
            id=int(r["id"]),
            name=r["name"],
            servings=int(r["servings"]),
            cuisine=r["cuisine"],
            staple=str(r["staple"]).upper() == "TRUE",
            ingredients=ingredients,
        )

    @staticmethod
    def _parse_datetime(s: str) -> datetime:
        """Parse a datetime string tolerating Google Sheets' reformatted format."""
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _row_to_plan(r: dict) -> WeekPlan:
        meals = {day: int(r[day]) for day in DAYS if r.get(day)}
        confirmed_at = None
        if r.get("confirmed_at"):
            confirmed_at = SheetsClient._parse_datetime(str(r["confirmed_at"]))
        return WeekPlan(
            week_start=date.fromisoformat(str(r["week_start"])),
            meals=meals,
            status=r["status"],
            created_at=SheetsClient._parse_datetime(str(r["created_at"])),
            confirmed_at=confirmed_at,
        )

    @staticmethod
    def _plan_to_row(plan: WeekPlan) -> list:
        return [
            plan.week_start.isoformat(),
            plan.meals.get("mon", ""),
            plan.meals.get("tue", ""),
            plan.meals.get("wed", ""),
            plan.meals.get("thu", ""),
            plan.meals.get("fri", ""),
            plan.meals.get("sat", ""),
            plan.meals.get("sun", ""),
            plan.status,
            plan.created_at.isoformat(),
            plan.confirmed_at.isoformat() if plan.confirmed_at else "",
        ]
