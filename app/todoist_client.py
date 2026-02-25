from typing import Optional, Iterator
from requests.exceptions import ConnectionError as RequestsConnectionError

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task

from app.models import Ingredient, IngredientMapping


def _flat(paginator: Iterator) -> list:
    """Flatten a paginated Todoist iterator into a plain list."""
    return [item for page in paginator for item in page]


class TodoistClient:
    def __init__(self, api_token: str, project_name: str = "Italian Store"):
        self._token = api_token
        self._project_name = project_name
        self._api = TodoistAPI(api_token)
        self._project_id = self._get_project_id(project_name)
        self._section_ids = self._cache_sections()

    def _reconnect(self) -> None:
        """Replace the API session with a fresh one after a dropped connection."""
        self._api = TodoistAPI(self._token)
        self._project_id = self._get_project_id(self._project_name)
        self._section_ids = self._cache_sections()

    # ------------------------------------------------------------------
    # Internal setup
    # ------------------------------------------------------------------

    def _get_project_id(self, name: str) -> str:
        for project in _flat(self._api.get_projects()):
            if project.name == name:
                return project.id
        raise ValueError(f"Todoist project '{name}' not found")

    def _cache_sections(self) -> dict[str, str]:
        sections = _flat(self._api.get_sections(project_id=self._project_id))
        return {s.name: s.id for s in sections}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all_tasks(self) -> list[Task]:
        try:
            return _flat(self._api.get_tasks(project_id=self._project_id))
        except RequestsConnectionError:
            self._reconnect()
            return _flat(self._api.get_tasks(project_id=self._project_id))

    def get_completed_tasks(self) -> list[Task]:
        return []

    def uncomplete_task(self, task_id: str) -> None:
        self._api.uncomplete_task(task_id=task_id)

    def close_task(self, task_id: str) -> None:
        self._api.complete_task(task_id=task_id)

    def add_task(
        self,
        name: str,
        section: str,
        description: str = "",
    ) -> Task:
        section_id = self._section_ids.get(section) or self._section_ids.get("Other")
        try:
            return self._api.add_task(
                content=name,
                project_id=self._project_id,
                section_id=section_id,
                description=description or None,
            )
        except RequestsConnectionError:
            self._reconnect()
            section_id = self._section_ids.get(section) or self._section_ids.get("Other")
            return self._api.add_task(
                content=name,
                project_id=self._project_id,
                section_id=section_id,
                description=description or None,
            )

    def find_task_by_name(self, name: str) -> Optional[Task]:
        name_lower = name.lower()
        for task in self.get_all_tasks():
            if name_lower in task.content.lower() or task.content.lower() in name_lower:
                return task
        return None

    def delete_all_tasks(self) -> None:
        for task in self.get_all_tasks():
            self._api.delete_task(task_id=task.id)

    def sync_shopping_list(
        self,
        ingredients: list[Ingredient],
        mappings: dict[str, IngredientMapping],
    ) -> dict:
        existing_tasks = self.get_all_tasks()
        existing_by_name = {t.content.lower(): t for t in existing_tasks}

        added: list[str] = []
        updated: list[str] = []
        skipped: list[str] = []

        for ingredient in ingredients:
            section = self._map_ingredient_to_section(ingredient.name, mappings)
            display = self._format_ingredient(ingredient)

            matched_task = None
            for task_name, task in existing_by_name.items():
                if ingredient.name.lower() in task_name:
                    matched_task = task
                    break

            if matched_task:
                skipped.append(display)
            else:
                self.add_task(name=display, section=section)
                added.append(display)

        return {"added": added, "updated": updated, "skipped": skipped}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_ingredient(ingredient: Ingredient) -> str:
        qty = (
            int(ingredient.quantity)
            if ingredient.quantity == int(ingredient.quantity)
            else ingredient.quantity
        )
        if ingredient.unit:
            return f"{ingredient.name} ({qty} {ingredient.unit})"
        return f"{ingredient.name} (x{qty})"

    @staticmethod
    def _map_ingredient_to_section(
        ingredient_name: str, mappings: dict[str, IngredientMapping]
    ) -> str:
        name_lower = ingredient_name.lower()
        for keyword, mapping in mappings.items():
            if keyword in name_lower:
                return mapping.todoist_section
        return "Other"
