from __future__ import annotations

from teacher_helper.use_cases.chat_orchestrator import (
    clarification_blocks_paid_tools,
    history_confirms_music,
    is_paid_budget_module,
    music_generation_needs_confirm,
    polish_monthly_limit_skip_message,
)


def test_clarification_blocks_paid_when_ask_and_generate() -> None:
    assert clarification_blocks_paid_tools({"ask_clarification", "generate_music"}) is True


def test_clarification_blocks_paid_for_video_confirm_and_graphics() -> None:
    assert clarification_blocks_paid_tools({"request_video_confirmation", "generate_graphics"}) is True


def test_prepare_project_blocks_paid_generate() -> None:
    assert clarification_blocks_paid_tools({"prepare_create_teacher_project", "generate_scenario"}) is True
    assert clarification_blocks_paid_tools({"prepare_delete_teacher_project", "export_library_file"}) is True


def test_clarification_does_not_block_search_or_reply_only() -> None:
    assert clarification_blocks_paid_tools({"ask_clarification", "search_library_fragments", "reply_to_user"}) is True
    assert clarification_blocks_paid_tools({"search_library_fragments", "search_web", "reply_to_user"}) is False


def test_generate_alone_is_not_blocked_by_clarification_policy() -> None:
    assert clarification_blocks_paid_tools({"generate_music"}) is False
    assert clarification_blocks_paid_tools({"edit_presentation"}) is False


def test_music_needs_confirm_without_history() -> None:
    assert music_generation_needs_confirm({"generate_music"}, []) is True


def test_music_does_not_need_confirm_after_user_says_tak() -> None:
    history = [
        ("user", "Zrób piosenkę o wodzie"),
        ("assistant", "Szacowany koszt: ~$0.26 USD\n\nCzy potwierdzasz generację muzyki? Napisz **tak**."),
        ("user", "tak"),
    ]
    assert history_confirms_music(history) is True
    assert music_generation_needs_confirm({"generate_music"}, history) is False


def test_music_confirm_rejected_on_unrelated_followup() -> None:
    history = [
        ("assistant", "Czy potwierdzasz generację muzyki? Napisz **tak**."),
        ("user", "nie, zmień temat"),
    ]
    assert history_confirms_music(history) is False
    assert music_generation_needs_confirm({"generate_music"}, history) is True


def test_music_confirm_does_not_treat_ok_as_yes() -> None:
    history = [
        ("assistant", "Czy potwierdzasz generację muzyki? Napisz **tak**."),
        ("user", "ok, zrób raczej grafikę"),
    ]
    assert history_confirms_music(history) is False


def test_music_confirm_is_one_shot_not_lifetime() -> None:
    history = [
        ("assistant", "Czy potwierdzasz generację muzyki? Napisz **tak**."),
        ("user", "tak"),
        ("assistant", "Gotowa piosenka o wodzie."),
    ]
    assert history_confirms_music(history) is False
    assert music_generation_needs_confirm({"generate_music"}, history) is True


def test_music_confirm_not_required_when_music_not_requested() -> None:
    assert music_generation_needs_confirm({"generate_graphics"}, []) is False


def test_paid_budget_modules() -> None:
    assert is_paid_budget_module("music") is True
    assert is_paid_budget_module("graphics") is True
    assert is_paid_budget_module("video") is True
    assert is_paid_budget_module("sound") is True
    assert is_paid_budget_module("study") is False
    assert is_paid_budget_module("scenario") is False


def test_polish_monthly_limit_skip_message_keeps_http_detail() -> None:
    msg = polish_monthly_limit_skip_message("Osiągnięto miesięczny limit kosztu LLM ($10.00, UTC).")
    assert "limit kosztu" in msg
    assert polish_monthly_limit_skip_message({"code": "x"}) == (
        "Osiągnięto miesięczny limit kosztu. Pominięto pozostałe płatne narzędzia."
    )


def test_music_variants_field_default_is_one() -> None:
    from teacher_helper.config import Settings

    assert Settings.model_fields["music_variants_per_provider"].default == 1
