import pytest

from pages.kendo import select_exact_option


class Item:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.clicked = False

    async def inner_text(self) -> str:
        return self.text

    async def click(self) -> None:
        self.clicked = True


class Collection:
    def __init__(self, items) -> None:
        self.items = list(items)

    @property
    def last(self):
        return self.items[-1]

    async def count(self) -> int:
        return len(self.items)

    def nth(self, index: int):
        return self.items[index]


class Listbox:
    def __init__(self, options) -> None:
        self.options = Collection(options)

    async def wait_for(self, *, state: str) -> None:
        assert state == "visible"

    def locator(self, selector: str):
        assert selector == '[role="option"]'
        return self.options


class Container:
    def __init__(self) -> None:
        self.arrow = Item()

    async def count(self) -> int:
        return 1

    def locator(self, selector: str):
        assert selector == ".k-select"
        return self.arrow


class FakePage:
    def __init__(self, old_listbox: Listbox, new_listbox: Listbox) -> None:
        self.container = Container()
        self.listboxes = Collection([old_listbox, new_listbox])
        self.waits = []

    def locator(self, selector: str):
        if selector == "#target":
            return self.container
        if selector == '[role="listbox"]:visible':
            return self.listboxes
        raise AssertionError(selector)

    async def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


@pytest.mark.asyncio
async def test_selects_from_newest_popup_when_previous_popup_is_still_visible() -> None:
    old_match = Item("اهل تسنن - شافعی")
    new_match = Item("اهل تسنن - شافعی")
    page = FakePage(Listbox([old_match]), Listbox([new_match]))

    await select_exact_option(page, "#target", "اهل تسنن - شافعی")

    assert page.container.arrow.clicked
    assert new_match.clicked
    assert not old_match.clicked
    assert page.waits == [100]
