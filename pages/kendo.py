"""Reliable helpers for SIDA's animated Kendo ComboBox popups."""

from __future__ import annotations

from typing import Any

from errors import PageTransitionError
from mappings import normalize_text


async def select_exact_option(
    page: Any,
    container_selector: str,
    expected: str,
) -> None:
    """Select exact text from the newest matching visible popup.

    Kendo can briefly leave the previous ComboBox popup visible during its
    closing animation. Searching visible popups from newest to oldest avoids
    treating that animation overlap as an ambiguous form state.
    """
    containers = page.locator(container_selector)
    if await containers.count() != 1:
        raise PageTransitionError(
            f"Expected one ComboBox container: {container_selector}"
        )

    await containers.locator(".k-select").click()
    listboxes = page.locator('[role="listbox"]:visible')
    await listboxes.last.wait_for(state="visible")

    expected_normalized = normalize_text(expected)
    for listbox_index in reversed(range(await listboxes.count())):
        options = listboxes.nth(listbox_index).locator('[role="option"]')
        for option_index in range(await options.count()):
            option = options.nth(option_index)
            if normalize_text(await option.inner_text()) == expected_normalized:
                await option.click()
                # Let Kendo finish closing this popup before the next ComboBox.
                await page.wait_for_timeout(100)
                return

    raise PageTransitionError(
        f"Required option {expected!r} was not available in {container_selector}."
    )
