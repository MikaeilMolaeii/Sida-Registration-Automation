"""Navigate through the confirmed SIDA menu back to preschool preregistration."""

from __future__ import annotations

from logging import Logger
from typing import Any

from errors import PageTransitionError
from mappings import normalize_text


class StartPageNavigator:
    START_ROUTE = "**/#/elementarySchool"
    LANDING_ACTIONS = 'button[ng-click="setAction(action)"]:visible'
    SEARCH_MARKER = "#combo-box-type-supervisorStatusId .k-select:visible"
    LATER_STAGE_MARKERS = (
        "#combo-box-din-type:visible, #studentMobileNumber:visible, "
        "#combo-box-type-hayat1:visible, #combo-box-type-hayat:visible, "
        "#combo-box-gradeTypeId:visible, #name:visible"
    )

    def __init__(self, page: Any, logger: Logger, *, timeout_ms: int = 15_000) -> None:
        self.page = page
        self.logger = logger
        self.timeout_ms = timeout_ms

    async def _click_exact(self, selector: str, expected: str) -> None:
        candidates = self.page.locator(selector)
        matches = []
        for index in range(await candidates.count()):
            candidate = candidates.nth(index)
            if normalize_text(await candidate.inner_text()) == normalize_text(expected):
                matches.append(candidate)
        if len(matches) != 1:
            raise PageTransitionError(
                f"Expected one SIDA menu item {expected!r}; found {len(matches)}."
            )
        await matches[0].click()

    async def _open_menu_level(
        self,
        *,
        parent_selector: str,
        parent_text: str,
        child_selector: str,
        child_text: str,
    ) -> None:
        """Click a menu level and leave its child visible, even if it was open."""
        await self._click_exact(parent_selector, parent_text)
        child = self.page.locator(child_selector).filter(has_text=child_text)
        try:
            await child.first.wait_for(state="visible", timeout=800)
            return
        except Exception:
            # The first click closed an already-expanded level; reopen it.
            await self._click_exact(parent_selector, parent_text)
        try:
            await child.first.wait_for(state="visible", timeout=self.timeout_ms)
        except Exception as exc:
            raise PageTransitionError(
                f"SIDA menu level {parent_text!r} did not open."
            ) from exc

    async def open_preschool_preregistration(self, *, force_menu: bool = False) -> None:
        # This makes recovery safe when a previous run already reached either
        # the search form or the elementary-school landing page.
        if not force_menu and (
            await self.page.locator(self.SEARCH_MARKER).count()
            and await self.page.locator(self.LATER_STAGE_MARKERS).count() == 0
        ):
            self.logger.info("Preschool preregistration search page is already open")
            return
        if not force_menu and await self._open_form_from_landing_if_available():
            return

        await self._open_menu_path()
        try:
            await self.page.wait_for_url(self.START_ROUTE, timeout=self.timeout_ms)
            await self.page.locator(self.LANDING_ACTIONS).first.wait_for(
                state="visible", timeout=self.timeout_ms
            )
        except Exception as exc:
            raise PageTransitionError(
                "The preschool preregistration landing page did not become ready."
            ) from exc
        if not await self._open_form_from_landing_if_available():
            raise PageTransitionError(
                "The preschool preregistration action was not available."
            )

    async def _open_menu_path(self) -> None:
        await self._open_menu_level(
            parent_selector="#right-menu-system a.ng-binding:visible",
            parent_text="عملیات اولیه",
            child_selector=(
                '#accordion-right-menu a[ng-click="setSubMenu($event)"]:visible'
            ),
            child_text="عملیات پیش ثبت نام",
        )
        await self._open_menu_level(
            parent_selector=(
                '#accordion-right-menu a[ng-click="setSubMenu($event)"]:visible'
            ),
            parent_text="عملیات پیش ثبت نام",
            child_selector=(
                '#accordion-right-menu a[href="#/elementarySchool"]:visible'
            ),
            child_text="پیش ثبت نام کودکستان",
        )
        await self._click_exact(
            '#accordion-right-menu a[href="#/elementarySchool"]:visible',
            "پیش ثبت نام کودکستان",
        )

    async def _open_form_from_landing_if_available(self) -> bool:
        actions = self.page.locator(self.LANDING_ACTIONS)
        matching = []
        for index in range(await actions.count()):
            action = actions.nth(index)
            if normalize_text(await action.inner_text()) == "پیش ثبت نام کودکستان":
                matching.append(action)
        if not matching:
            return False
        if len(matching) != 1:
            raise PageTransitionError(
                "Expected one preschool preregistration landing-page action."
            )
        await matching[0].click()
        try:
            await self.page.locator(self.SEARCH_MARKER).wait_for(
                state="visible", timeout=self.timeout_ms
            )
        except Exception as exc:
            raise PageTransitionError(
                "The preschool preregistration search form did not become ready."
            ) from exc
        self.logger.info("Returned to the preschool preregistration start page")
        return True
