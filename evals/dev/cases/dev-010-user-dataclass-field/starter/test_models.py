import pytest

from models import Product


def test_product_holds_name_and_price():
    product = Product("widget", 9.99)
    assert product.name == "widget"
    assert product.price == 9.99


def test_product_rejects_negative_price():
    with pytest.raises(ValueError):
        Product("widget", -1)
