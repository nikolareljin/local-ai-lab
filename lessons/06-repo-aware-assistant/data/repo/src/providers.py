"""Embedding providers. Add a new embedding provider by registering it here."""

PROVIDERS = {
    "hash": lambda text: hash(text),
}


def register(name, embed):
    """Add a new provider so retrieval can select it by name."""
    PROVIDERS[name] = embed


def get_provider(name="hash"):
    """Look up a registered embedding provider by name."""
    return PROVIDERS[name]
