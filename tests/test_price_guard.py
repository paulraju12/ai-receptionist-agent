"""The price guardrail must stop the model from attaching a real price to the wrong service."""
from app.agent import load_tenant, price_is_grounded

KNOWLEDGE = load_tenant("demo-dental")["knowledge"]


def test_blocks_crown_priced_at_whitening_rate():
    # $299 is a real price - but it belongs to teeth whitening, not crowns.
    reply = "A crown starts at $299. Would you like to book?"
    assert not price_is_grounded(KNOWLEDGE, reply, "How much is a crown?")


def test_allows_real_cleaning_price():
    reply = "A cleaning costs $89 for new patients, normally $140."
    assert price_is_grounded(KNOWLEDGE, reply, "How much is a cleaning?")


def test_allows_whitening_at_its_own_price():
    reply = "Teeth whitening starts from $299."
    assert price_is_grounded(KNOWLEDGE, reply, "How much is whitening?")
