"""
Telegram bot handlers for the meal planner.

Conversation states
-------------------
PLAN_*   - /plan flow
ADD_*    - /add flow
GEN_*    - /generate flow
"""

import logging
from datetime import datetime
from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.models import DAY_LABELS, DAYS, Meal, WeekPlan
from app.meal_planner import MealPlanner

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------

(
    PLAN_GENERATED,
    PLAN_SWAPPING,
    PLAN_REPLACING,
    PLAN_PICKING_DAY,
) = range(4)

(
    ADD_NAME,
    ADD_INGREDIENTS,
    ADD_SERVINGS,
    ADD_CUISINE,
    ADD_CONFIRM,
) = range(10, 15)

(
    GEN_CUISINE,
    GEN_CONSTRAINTS,
    GEN_PICK,
) = range(20, 23)

(
    EDIT_SELECT,
    EDIT_INGREDIENTS,
    EDIT_SERVINGS,
    EDIT_CUISINE,
    EDIT_CONFIRM,
) = range(30, 35)

(
    RECIPE_SELECT,
    RECIPE_NOTES,
    RECIPE_VIEW,
) = range(40, 43)

TODAY_NOTES = 50

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _planner(context: ContextTypes.DEFAULT_TYPE) -> MealPlanner:
    return context.bot_data["planner"]


def _format_plan(plan: WeekPlan, meals_by_id: dict[int, Meal]) -> str:
    lines = [f"*Week of {plan.week_start.strftime('%b %d, %Y')}*\n"]
    for day in DAYS:
        meal_id = plan.meals.get(day)
        meal_name = meals_by_id.get(meal_id, Meal(id=0, name="?", servings=0, cuisine="", staple=False, ingredients=[])).name if meal_id else "—"
        lines.append(f"*{DAY_LABELS[day]}:* {meal_name}")
    return "\n".join(lines)


def _plan_keyboard(plan: WeekPlan) -> InlineKeyboardMarkup:
    rows = []
    for day in DAYS:
        rows.append([
            InlineKeyboardButton(f"↕ {DAY_LABELS[day][:3]}", callback_data=f"swap_pick:{day}"),
            InlineKeyboardButton(f"✏ {DAY_LABELS[day][:3]}", callback_data=f"replace_pick:{day}"),
        ])
    rows.append([
        InlineKeyboardButton("✅ Confirm", callback_data="confirm"),
        InlineKeyboardButton("🔀 Reshuffle", callback_data="reshuffle"),
    ])
    return InlineKeyboardMarkup(rows)


def _meals_keyboard(
    meals: list[Meal],
    prefix: str,
    cols: int = 2,
    include_generate: bool = True,
) -> InlineKeyboardMarkup:
    rows = []
    row: list[InlineKeyboardButton] = []
    for meal in meals[:20]:  # cap at 20 buttons
        row.append(InlineKeyboardButton(meal.name, callback_data=f"{prefix}:{meal.id}"))
        if len(row) == cols:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if include_generate:
        rows.append([InlineKeyboardButton("✨ Generate new with Claude", callback_data=f"{prefix}:generate")])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)


def _days_keyboard(prefix: str, exclude_day: Optional[str] = None) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(DAY_LABELS[d][:3], callback_data=f"{prefix}:{d}")
        for d in DAYS if d != exclude_day
    ]
    rows = [row[:4], row[4:]] if len(row) > 4 else [row]
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)


async def _load_plan_meals(planner: MealPlanner, plan: WeekPlan) -> dict[int, Meal]:
    meals_by_id: dict[int, Meal] = {}
    for meal_id in set(plan.meals.values()):
        meal = planner._sheets.get_meal_by_id(meal_id)
        if meal:
            meals_by_id[meal_id] = meal
    return meals_by_id


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 *Meal Planner Bot*\n\n"
        "Commands:\n"
        "/plan — Generate and confirm this week's dinner plan\n"
        "/add — Add a new meal to the library\n"
        "/edit — Edit an existing meal in the library\n"
        "/recipe — View or generate a recipe for a meal\n"
        "/today — Show today's planned meal with ingredients and recipe\n"
        "/generate — Generate meal ideas with Claude\n"
        "/meals — List all meals in the library\n"
        "/shopping — Show current shopping list status\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# /plan flow
# ---------------------------------------------------------------------------


async def plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("⏳ Generating your week plan…")
    planner = _planner(context)
    try:
        plan = planner.generate_week_plan()
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return ConversationHandler.END
    meals_by_id = await _load_plan_meals(planner, plan)
    context.user_data["plan"] = plan
    context.user_data["meals_by_id"] = meals_by_id

    text = _format_plan(plan, meals_by_id)
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_plan_keyboard(plan),
    )
    return PLAN_GENERATED


async def handle_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    planner = _planner(context)
    plan: WeekPlan = context.user_data.get("plan")

    if data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    if data == "reshuffle":
        await query.edit_message_text("⏳ Reshuffling…")
        plan = planner.generate_week_plan()
        meals_by_id = await _load_plan_meals(planner, plan)
        context.user_data["plan"] = plan
        context.user_data["meals_by_id"] = meals_by_id
        await query.edit_message_text(
            _format_plan(plan, meals_by_id),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_plan_keyboard(plan),
        )
        return PLAN_GENERATED

    if data == "confirm":
        await query.edit_message_text("⏳ Confirming plan and syncing to Todoist…")
        result = planner.confirm_plan(plan)
        shopping = result["shopping"]
        added = len(shopping["added"])
        skipped = len(shopping["skipped"])
        text = (
            f"✅ *Plan confirmed!*\n\n"
            f"Shopping list updated:\n"
            f"• {added} item(s) added\n"
            f"• {skipped} item(s) already on list\n\n"
            f"Check Todoist for the full list."
        )
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    if data.startswith("swap_pick:"):
        day = data.split(":")[1]
        context.user_data["swap_day1"] = day
        await query.edit_message_text(
            f"Select a day to swap with *{DAY_LABELS[day]}*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_days_keyboard("swap_do", exclude_day=day),
        )
        return PLAN_SWAPPING

    if data.startswith("replace_pick:"):
        day = data.split(":")[1]
        context.user_data["replace_day"] = day
        current_id = plan.meals.get(day)
        options = planner.get_meal_options(exclude_ids=[current_id] if current_id else [])
        await query.edit_message_text(
            f"Choose a replacement for *{DAY_LABELS[day]}*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_meals_keyboard(options, prefix="replace_do"),
        )
        return PLAN_REPLACING

    return PLAN_GENERATED


async def handle_swap_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    planner = _planner(context)
    plan: WeekPlan = context.user_data.get("plan")

    if data == "cancel":
        meals_by_id = context.user_data.get("meals_by_id", {})
        await query.edit_message_text(
            _format_plan(plan, meals_by_id),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_plan_keyboard(plan),
        )
        return PLAN_GENERATED

    if data.startswith("swap_do:"):
        day2 = data.split(":")[1]
        day1 = context.user_data["swap_day1"]
        plan = planner.swap_days(plan, day1, day2)
        meals_by_id = await _load_plan_meals(planner, plan)
        context.user_data["plan"] = plan
        context.user_data["meals_by_id"] = meals_by_id
        await query.edit_message_text(
            _format_plan(plan, meals_by_id),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_plan_keyboard(plan),
        )
        return PLAN_GENERATED

    return PLAN_SWAPPING


async def handle_replace_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    planner = _planner(context)
    plan: WeekPlan = context.user_data.get("plan")

    if data == "cancel":
        meals_by_id = context.user_data.get("meals_by_id", {})
        await query.edit_message_text(
            _format_plan(plan, meals_by_id),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_plan_keyboard(plan),
        )
        return PLAN_GENERATED

    if data.startswith("replace_do:"):
        raw_id = data.split(":")[1]
        if raw_id == "generate":
            await query.edit_message_text("⏳ Generating meal ideas with Claude…")
            meals = planner._claude.generate_meal_ideas(
                existing_meals=planner._sheets.get_all_meals(), count=3
            )
            context.user_data["generated_meals"] = meals
            day = context.user_data.get("replace_day", "mon")
            await query.edit_message_text(
                f"Pick a generated meal for *{DAY_LABELS[day]}*:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_meals_keyboard(meals, prefix="replace_generated", include_generate=False),
            )
            return PLAN_REPLACING

        meal_id = int(raw_id)
        day = context.user_data.get("replace_day", "mon")
        plan = planner.replace_meal(plan, day, meal_id)
        meals_by_id = await _load_plan_meals(planner, plan)
        context.user_data["plan"] = plan
        context.user_data["meals_by_id"] = meals_by_id
        await query.edit_message_text(
            _format_plan(plan, meals_by_id),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_plan_keyboard(plan),
        )
        return PLAN_GENERATED

    if data.startswith("replace_generated:"):
        idx = int(data.split(":")[1])
        generated = context.user_data.get("generated_meals", [])
        meal = generated[idx]
        new_id = planner._sheets.add_meal(meal)
        day = context.user_data.get("replace_day", "mon")
        plan = planner.replace_meal(plan, day, new_id)
        meals_by_id = await _load_plan_meals(planner, plan)
        context.user_data["plan"] = plan
        context.user_data["meals_by_id"] = meals_by_id
        await query.edit_message_text(
            _format_plan(plan, meals_by_id),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_plan_keyboard(plan),
        )
        return PLAN_GENERATED

    return PLAN_REPLACING


# ---------------------------------------------------------------------------
# /add flow (ConversationHandler)
# ---------------------------------------------------------------------------


async def add_meal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_meal"] = {}
    await update.message.reply_text("🍽 What's the meal called?")
    return ADD_NAME


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_meal"]["name"] = update.message.text.strip()
    await update.message.reply_text(
        "📝 List the ingredients with quantities.\n\n"
        "Example:\n"
        "2 chicken breasts\n"
        "1 can chickpeas\n"
        "3 cloves garlic\n"
        "1 tsp cumin"
    )
    return ADD_INGREDIENTS


async def add_ingredients(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    await update.message.reply_text("⏳ Parsing ingredients…")
    planner = _planner(context)
    try:
        ingredients = planner._claude.parse_ingredients(raw)
        context.user_data["new_meal"]["ingredients"] = ingredients
        context.user_data["new_meal"].setdefault("servings", 4)
        context.user_data["new_meal"].setdefault("cuisine", "")
        context.user_data["new_meal"].setdefault("staple", False)
        return await _show_add_confirm(update, context)
    except Exception as e:
        log.error("Failed to parse ingredients: %s", e)
        await update.message.reply_text(
            "⚠️ Couldn't parse that. Try again with one ingredient per line."
        )
        return ADD_INGREDIENTS


async def _show_add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    meal_data = context.user_data["new_meal"]
    ing_lines = "\n".join(
        f"  • {i.name} ({i.quantity} {i.unit})".rstrip()
        for i in meal_data["ingredients"]
    )
    text = (
        f"*{meal_data['name']}*\n"
        f"Servings: {meal_data['servings']}\n"
        f"Cuisine: {meal_data['cuisine'] or '(not set)'}\n"
        f"Staple: {'✅' if meal_data['staple'] else '❌'}\n\n"
        f"Ingredients:\n{ing_lines}"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💾 Save", callback_data="add_save"),
            InlineKeyboardButton("❌ Cancel", callback_data="add_cancel"),
        ],
        [
            InlineKeyboardButton("🍽 Edit servings", callback_data="add_edit_servings"),
            InlineKeyboardButton("🌍 Set cuisine", callback_data="add_edit_cuisine"),
        ],
        [
            InlineKeyboardButton("⭐ Toggle staple", callback_data="add_toggle_staple"),
        ],
    ])
    msg = update.message or (update.callback_query and update.callback_query.message)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    return ADD_CONFIRM


async def handle_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    planner = _planner(context)

    if data == "add_cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    if data == "add_save":
        meal_data = context.user_data["new_meal"]
        from app.models import Meal as MealModel
        meal = MealModel(
            id=0,
            name=meal_data["name"],
            servings=meal_data["servings"],
            cuisine=meal_data["cuisine"],
            staple=meal_data["staple"],
            ingredients=meal_data["ingredients"],
        )
        new_id = planner._sheets.add_meal(meal)
        await query.edit_message_text(
            f"✅ *{meal.name}* saved to library (ID: {new_id}).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    if data == "add_toggle_staple":
        context.user_data["new_meal"]["staple"] = not context.user_data["new_meal"]["staple"]
        return await _show_add_confirm(update, context)

    if data == "add_edit_servings":
        await query.edit_message_text("How many servings does this make? (Enter a number)")
        return ADD_SERVINGS

    if data == "add_edit_cuisine":
        await query.edit_message_text(
            "What cuisine is this?\n\nExamples: Italian, Mexican, Asian, American, Mediterranean, Indian, Middle Eastern"
        )
        return ADD_CUISINE

    return ADD_CONFIRM


async def add_servings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["new_meal"]["servings"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Please enter a number.")
        return ADD_SERVINGS
    return await _show_add_confirm(update, context)


async def add_cuisine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_meal"]["cuisine"] = update.message.text.strip().title()
    return await _show_add_confirm(update, context)


# ---------------------------------------------------------------------------
# /generate flow
# ---------------------------------------------------------------------------


async def generate_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Italian", callback_data="gen_cuisine:Italian"),
            InlineKeyboardButton("Mexican", callback_data="gen_cuisine:Mexican"),
            InlineKeyboardButton("Asian", callback_data="gen_cuisine:Asian"),
        ],
        [
            InlineKeyboardButton("American", callback_data="gen_cuisine:American"),
            InlineKeyboardButton("Mediterranean", callback_data="gen_cuisine:Mediterranean"),
            InlineKeyboardButton("Indian", callback_data="gen_cuisine:Indian"),
        ],
        [
            InlineKeyboardButton("Any cuisine", callback_data="gen_cuisine:any"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ],
    ])
    await update.message.reply_text(
        "✨ *Generate meal ideas*\n\nWhat cuisine?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )
    return GEN_CUISINE


async def handle_gen_cuisine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    cuisine = data.split(":")[1]
    context.user_data["gen_cuisine"] = None if cuisine == "any" else cuisine

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Quick & easy", callback_data="gen_constraints:quick"),
            InlineKeyboardButton("Vegetarian", callback_data="gen_constraints:vegetarian"),
        ],
        [
            InlineKeyboardButton("Healthy", callback_data="gen_constraints:healthy"),
            InlineKeyboardButton("No constraints", callback_data="gen_constraints:none"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])
    await query.edit_message_text(
        "Any constraints?",
        reply_markup=keyboard,
    )
    return GEN_CONSTRAINTS


async def handle_gen_constraints(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    constraints = data.split(":")[1]
    context.user_data["gen_constraints"] = None if constraints == "none" else constraints

    await query.edit_message_text("⏳ Generating ideas with Claude…")
    planner = _planner(context)
    meals = planner._claude.generate_meal_ideas(
        existing_meals=planner._sheets.get_all_meals(),
        cuisine=context.user_data.get("gen_cuisine"),
        constraints=context.user_data.get("gen_constraints"),
        count=3,
    )
    context.user_data["gen_meals"] = meals

    lines = []
    for i, meal in enumerate(meals):
        ing_preview = ", ".join(ing.name for ing in meal.ingredients[:4])
        if len(meal.ingredients) > 4:
            ing_preview += f" +{len(meal.ingredients) - 4} more"
        lines.append(f"*{i + 1}. {meal.name}*\n_{ing_preview}_")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💾 Save #{i+1}", callback_data=f"gen_save:{i}") for i in range(len(meals))],
        [InlineKeyboardButton("💾 Save all", callback_data="gen_save:all")],
        [InlineKeyboardButton("✨ Generate more", callback_data="gen_more")],
        [InlineKeyboardButton("Done", callback_data="cancel")],
    ])
    await query.edit_message_text(
        "\n\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )
    return GEN_PICK


async def handle_gen_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    planner = _planner(context)
    meals = context.user_data.get("gen_meals", [])

    if data == "cancel":
        await query.edit_message_text("Done generating.")
        return ConversationHandler.END

    if data == "gen_more":
        await query.edit_message_text("⏳ Generating more ideas…")
        meals = planner._claude.generate_meal_ideas(
            existing_meals=planner._sheets.get_all_meals(),
            cuisine=context.user_data.get("gen_cuisine"),
            constraints=context.user_data.get("gen_constraints"),
            count=3,
        )
        context.user_data["gen_meals"] = meals
        lines = []
        for i, meal in enumerate(meals):
            ing_preview = ", ".join(ing.name for ing in meal.ingredients[:4])
            if len(meal.ingredients) > 4:
                ing_preview += f" +{len(meal.ingredients) - 4} more"
            lines.append(f"*{i + 1}. {meal.name}*\n_{ing_preview}_")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💾 Save #{i+1}", callback_data=f"gen_save:{i}") for i in range(len(meals))],
            [InlineKeyboardButton("💾 Save all", callback_data="gen_save:all")],
            [InlineKeyboardButton("✨ Generate more", callback_data="gen_more")],
            [InlineKeyboardButton("Done", callback_data="cancel")],
        ])
        await query.edit_message_text(
            "\n\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
        return GEN_PICK

    if data == "gen_save:all":
        saved = []
        for meal in meals:
            new_id = planner._sheets.add_meal(meal)
            saved.append(f"• {meal.name} (ID: {new_id})")
        await query.edit_message_text(
            "✅ Saved:\n" + "\n".join(saved), parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    if data.startswith("gen_save:"):
        idx = int(data.split(":")[1])
        meal = meals[idx]
        new_id = planner._sheets.add_meal(meal)
        await query.edit_message_text(
            f"✅ *{meal.name}* saved to library (ID: {new_id}).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    return GEN_PICK


# ---------------------------------------------------------------------------
# /edit flow (ConversationHandler)
# ---------------------------------------------------------------------------


async def edit_meal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    planner = _planner(context)
    meals = planner._sheets.get_all_meals()
    if not meals:
        await update.message.reply_text("No meals yet. Use /add first.")
        return ConversationHandler.END
    await update.message.reply_text(
        "✏️ Which meal do you want to edit?",
        reply_markup=_meals_keyboard(meals, prefix="edit_select", include_generate=False),
    )
    return EDIT_SELECT


async def handle_edit_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    meal_id = int(data.split(":")[1])
    planner = _planner(context)
    meal = planner._sheets.get_meal_by_id(meal_id)
    if not meal:
        await query.edit_message_text("Meal not found.")
        return ConversationHandler.END

    context.user_data["edit_meal"] = {
        "id": meal.id,
        "name": meal.name,
        "servings": meal.servings,
        "cuisine": meal.cuisine,
        "staple": meal.staple,
        "ingredients": meal.ingredients,
    }
    return await _show_edit_confirm(update, context)


async def _show_edit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    meal_data = context.user_data["edit_meal"]
    ing_lines = "\n".join(
        f"  • {i.name} ({i.quantity} {i.unit})".rstrip()
        for i in meal_data["ingredients"]
    )
    text = (
        f"*{meal_data['name']}*\n"
        f"Servings: {meal_data['servings']}\n"
        f"Cuisine: {meal_data['cuisine'] or '(not set)'}\n"
        f"Staple: {'✅' if meal_data['staple'] else '❌'}\n\n"
        f"Ingredients:\n{ing_lines}"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💾 Save", callback_data="edit_save"),
            InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel"),
        ],
        [
            InlineKeyboardButton("📝 Edit ingredients", callback_data="edit_edit_ingredients"),
            InlineKeyboardButton("🍽 Edit servings", callback_data="edit_edit_servings"),
        ],
        [
            InlineKeyboardButton("🌍 Set cuisine", callback_data="edit_edit_cuisine"),
            InlineKeyboardButton("⭐ Toggle staple", callback_data="edit_toggle_staple"),
        ],
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    return EDIT_CONFIRM


async def handle_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    planner = _planner(context)

    if data == "edit_cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    if data == "edit_save":
        meal_data = context.user_data["edit_meal"]
        from app.models import Meal as MealModel
        meal = MealModel(
            id=meal_data["id"],
            name=meal_data["name"],
            servings=meal_data["servings"],
            cuisine=meal_data["cuisine"],
            staple=meal_data["staple"],
            ingredients=meal_data["ingredients"],
        )
        planner._sheets.update_meal(meal)
        await query.edit_message_text(
            f"✅ *{meal.name}* updated in library.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    if data == "edit_toggle_staple":
        context.user_data["edit_meal"]["staple"] = not context.user_data["edit_meal"]["staple"]
        return await _show_edit_confirm(update, context)

    if data == "edit_edit_servings":
        await query.edit_message_text("How many servings does this make? (Enter a number)")
        return EDIT_SERVINGS

    if data == "edit_edit_cuisine":
        await query.edit_message_text(
            "What cuisine is this?\n\nExamples: Italian, Mexican, Asian, American, Mediterranean, Indian, Middle Eastern"
        )
        return EDIT_CUISINE

    if data == "edit_edit_ingredients":
        meal_data = context.user_data["edit_meal"]
        current = "\n".join(
            f"  • {i.name} ({i.quantity} {i.unit})".rstrip()
            for i in meal_data["ingredients"]
        )
        await query.edit_message_text(
            f"*Current ingredients:*\n{current}\n\n"
            "📝 Reply with the new ingredient list (one per line with quantities).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return EDIT_INGREDIENTS

    return EDIT_CONFIRM


async def edit_ingredients(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    await update.message.reply_text("⏳ Parsing ingredients…")
    planner = _planner(context)
    try:
        ingredients = planner._claude.parse_ingredients(raw)
        context.user_data["edit_meal"]["ingredients"] = ingredients
        return await _show_edit_confirm(update, context)
    except Exception as e:
        log.error("Failed to parse ingredients: %s", e)
        await update.message.reply_text(
            "⚠️ Couldn't parse that. Try again with one ingredient per line."
        )
        return EDIT_INGREDIENTS


async def edit_servings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["edit_meal"]["servings"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Please enter a number.")
        return EDIT_SERVINGS
    return await _show_edit_confirm(update, context)


async def edit_cuisine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["edit_meal"]["cuisine"] = update.message.text.strip().title()
    return await _show_edit_confirm(update, context)


# ---------------------------------------------------------------------------
# /recipe flow (ConversationHandler)
# ---------------------------------------------------------------------------


async def recipe_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    planner = _planner(context)
    meals = planner._sheets.get_all_meals()
    if not meals:
        await update.message.reply_text("No meals yet. Use /add first.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🍳 Which meal's recipe do you want?",
        reply_markup=_meals_keyboard(meals, prefix="recipe_select", include_generate=False),
    )
    return RECIPE_SELECT


async def handle_recipe_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    meal_id = int(data.split(":")[1])
    planner = _planner(context)
    meal = planner._sheets.get_meal_by_id(meal_id)
    if not meal:
        await query.edit_message_text("Meal not found.")
        return ConversationHandler.END

    context.user_data["recipe_meal_id"] = meal_id

    recipe = planner._sheets.get_recipe(meal_id)
    if recipe:
        return await _show_recipe(update, context, meal.name, recipe)

    # No recipe yet — ask for optional notes
    await query.edit_message_text(
        f"No recipe saved for *{meal.name}* yet.\n\n"
        "Add any notes for Claude (cooking method, dietary needs, skill level…) "
        "or tap Skip to generate now.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭ Skip", callback_data="recipe_skip_notes")],
            [InlineKeyboardButton("❌ Cancel", callback_data="recipe_cancel")],
        ]),
    )
    return RECIPE_NOTES


async def _show_recipe(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    meal_name: str,
    recipe: dict,
) -> int:
    notes_line = f"\n_Notes: {recipe['user_notes']}_" if recipe.get("user_notes") else ""
    text = f"*{meal_name} — Recipe*{notes_line}\n\n{recipe['instructions']}"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Regenerate", callback_data="recipe_regenerate"),
            InlineKeyboardButton("✅ Done", callback_data="recipe_done"),
        ]
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
    return RECIPE_VIEW


async def _generate_and_show_recipe(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_notes: str = "",
) -> int:
    planner = _planner(context)
    meal_id = context.user_data["recipe_meal_id"]
    meal = planner._sheets.get_meal_by_id(meal_id)

    instructions = planner._claude.generate_recipe(meal, user_notes=user_notes)
    planner._sheets.save_recipe(meal_id, instructions, user_notes=user_notes)

    recipe = {"instructions": instructions, "user_notes": user_notes}
    return await _show_recipe(update, context, meal.name, recipe)


async def handle_recipe_notes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles Skip and Cancel buttons while waiting for recipe notes."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "recipe_cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    if data == "recipe_skip_notes":
        await query.edit_message_text("⏳ Generating recipe…")
        return await _generate_and_show_recipe(update, context, user_notes="")

    return RECIPE_NOTES


async def recipe_notes_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User typed their notes; generate the recipe using them."""
    user_notes = update.message.text.strip()
    await update.message.reply_text("⏳ Generating recipe…")
    return await _generate_and_show_recipe(update, context, user_notes=user_notes)


async def handle_recipe_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "recipe_done":
        await query.edit_message_text("Done.")
        return ConversationHandler.END

    if data == "recipe_regenerate":
        await query.edit_message_text(
            "Add any notes for the regenerated recipe, or tap Skip.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭ Skip", callback_data="recipe_skip_notes")],
                [InlineKeyboardButton("❌ Cancel", callback_data="recipe_cancel")],
            ]),
        )
        return RECIPE_NOTES

    return RECIPE_VIEW


# ---------------------------------------------------------------------------
# /today command
# ---------------------------------------------------------------------------


def _format_today_text(meal_name: str, ing_lines: str, recipe: Optional[dict]) -> str:
    text = f"*Today: {meal_name}*\n\n*Ingredients:*\n{ing_lines}"
    if recipe:
        notes_line = f"\n_Notes: {recipe['user_notes']}_" if recipe.get("user_notes") else ""
        text += f"\n\n*Recipe:*{notes_line}\n{recipe['instructions']}"
    return text


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    planner = _planner(context)
    plan = planner._sheets.get_last_week_plan()
    if not plan:
        await update.message.reply_text("No confirmed week plan yet. Use /plan to create one.")
        return ConversationHandler.END

    today_key = datetime.now().strftime("%a").lower()  # "mon", "tue", …
    meal_id = plan.meals.get(today_key)
    if not meal_id:
        await update.message.reply_text("No meal planned for today.")
        return ConversationHandler.END

    meal = planner._sheets.get_meal_by_id(meal_id)
    if not meal:
        await update.message.reply_text("Meal not found in library.")
        return ConversationHandler.END

    context.user_data["recipe_meal_id"] = meal_id

    ing_lines = "\n".join(
        f"  • {i.name} ({i.quantity} {i.unit})".rstrip()
        for i in meal.ingredients
    )
    recipe = planner._sheets.get_recipe(meal_id)

    if recipe:
        await update.message.reply_text(
            _format_today_text(meal.name, ing_lines, recipe),
            parse_mode=ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    # No recipe yet — offer to generate
    context.user_data["today_ing_lines"] = ing_lines
    context.user_data["today_meal_name"] = meal.name
    await update.message.reply_text(
        _format_today_text(meal.name, ing_lines, None) + "\n\n_No recipe saved yet._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🍳 Generate recipe", callback_data="today_gen_recipe")],
            [InlineKeyboardButton("❌ Skip", callback_data="today_skip")],
        ]),
    )
    return TODAY_NOTES


async def handle_today_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data in ("today_skip", "today_cancel"):
        await query.edit_message_reply_markup(reply_markup=None)
        return ConversationHandler.END

    if data == "today_gen_recipe":
        await query.edit_message_text(
            query.message.text + "\n\nAdd any notes for Claude, or tap Skip to generate now.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭ Skip", callback_data="today_skip_notes")],
                [InlineKeyboardButton("❌ Cancel", callback_data="today_cancel")],
            ]),
        )
        return TODAY_NOTES

    if data == "today_skip_notes":
        await query.edit_message_text("⏳ Generating recipe…")
        return await _today_generate_and_show(update, context, user_notes="")

    return TODAY_NOTES


async def today_notes_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_notes = update.message.text.strip()
    await update.message.reply_text("⏳ Generating recipe…")
    return await _today_generate_and_show(update, context, user_notes=user_notes)


async def _today_generate_and_show(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_notes: str = "",
) -> int:
    planner = _planner(context)
    meal_id = context.user_data["recipe_meal_id"]
    meal = planner._sheets.get_meal_by_id(meal_id)
    instructions = planner._claude.generate_recipe(meal, user_notes=user_notes)
    planner._sheets.save_recipe(meal_id, instructions, user_notes=user_notes)

    ing_lines = context.user_data.get("today_ing_lines") or "\n".join(
        f"  • {i.name} ({i.quantity} {i.unit})".rstrip() for i in meal.ingredients
    )
    recipe = {"instructions": instructions, "user_notes": user_notes}
    text = _format_today_text(meal.name, ing_lines, recipe)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /meals
# ---------------------------------------------------------------------------


async def list_meals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    planner = _planner(context)
    meals = planner._sheets.get_all_meals()

    args = context.args or []
    cuisine_filter = args[0].lower() if args else None

    if cuisine_filter:
        meals = [m for m in meals if cuisine_filter in m.cuisine.lower()]

    if not meals:
        await update.message.reply_text("No meals found.")
        return

    # Group by cuisine
    by_cuisine: dict[str, list[Meal]] = {}
    for m in meals:
        by_cuisine.setdefault(m.cuisine or "Other", []).append(m)

    lines = [f"*Meal Library ({len(meals)} meals)*\n"]
    for cuisine, cms in sorted(by_cuisine.items()):
        lines.append(f"\n*{cuisine}*")
        for m in cms:
            staple = "⭐ " if m.staple else ""
            lines.append(f"  {staple}{m.name} (ID: {m.id}, serves {m.servings})")

    # Split into chunks of ~4000 chars
    text = "\n".join(lines)
    chunk_size = 4000
    for i in range(0, len(text), chunk_size):
        await update.message.reply_text(
            text[i : i + chunk_size], parse_mode=ParseMode.MARKDOWN
        )


# ---------------------------------------------------------------------------
# /shopping
# ---------------------------------------------------------------------------


async def shopping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    planner = _planner(context)
    tasks = planner._todoist.get_all_tasks()

    if not tasks:
        await update.message.reply_text("🛒 Shopping list is empty.")
        return

    lines = [f"🛒 *Shopping List ({len(tasks)} items)*\n"]
    # Group by section name (best effort from task.section_id)
    for task in tasks:
        lines.append(f"• {task.content}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------


def register_handlers(app: Application) -> None:
    # /start
    app.add_handler(CommandHandler("start", start))

    # /plan — inline-keyboard driven, no ConversationHandler needed for simplicity
    # We use a ConversationHandler to track state across callback queries
    plan_conv = ConversationHandler(
        entry_points=[CommandHandler("plan", plan)],
        states={
            PLAN_GENERATED: [
                CallbackQueryHandler(handle_plan_callback),
            ],
            PLAN_SWAPPING: [
                CallbackQueryHandler(handle_swap_callback),
            ],
            PLAN_REPLACING: [
                CallbackQueryHandler(handle_replace_callback),
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )
    app.add_handler(plan_conv)

    # /add
    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_meal_start)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_INGREDIENTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_ingredients)
            ],
            ADD_SERVINGS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_servings)
            ],
            ADD_CUISINE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_cuisine)
            ],
            ADD_CONFIRM: [CallbackQueryHandler(handle_add_callback)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )
    app.add_handler(add_conv)

    # /generate
    gen_conv = ConversationHandler(
        entry_points=[CommandHandler("generate", generate_start)],
        states={
            GEN_CUISINE: [CallbackQueryHandler(handle_gen_cuisine)],
            GEN_CONSTRAINTS: [CallbackQueryHandler(handle_gen_constraints)],
            GEN_PICK: [CallbackQueryHandler(handle_gen_pick)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )
    app.add_handler(gen_conv)

    # /edit
    edit_conv = ConversationHandler(
        entry_points=[CommandHandler("edit", edit_meal_start)],
        states={
            EDIT_SELECT: [CallbackQueryHandler(handle_edit_select_callback)],
            EDIT_INGREDIENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_ingredients)],
            EDIT_SERVINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_servings)],
            EDIT_CUISINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_cuisine)],
            EDIT_CONFIRM: [CallbackQueryHandler(handle_edit_callback)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )
    app.add_handler(edit_conv)

    # /recipe
    recipe_conv = ConversationHandler(
        entry_points=[CommandHandler("recipe", recipe_start)],
        states={
            RECIPE_SELECT: [CallbackQueryHandler(handle_recipe_select_callback)],
            RECIPE_NOTES: [
                CallbackQueryHandler(handle_recipe_notes_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, recipe_notes_text),
            ],
            RECIPE_VIEW: [CallbackQueryHandler(handle_recipe_view_callback)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )
    app.add_handler(recipe_conv)

    # /today
    today_conv = ConversationHandler(
        entry_points=[CommandHandler("today", today)],
        states={
            TODAY_NOTES: [
                CallbackQueryHandler(handle_today_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, today_notes_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )
    app.add_handler(today_conv)

    # /meals
    app.add_handler(CommandHandler("meals", list_meals))

    # /shopping
    app.add_handler(CommandHandler("shopping", shopping))
