"""Shared exception types for PromptLoop."""

from __future__ import annotations


class PromptLoopError(Exception):
    """Base class for all PromptLoop errors."""


class InputError(PromptLoopError):
    """Invalid or unreadable input data (CSV, template)."""


class TemplateError(PromptLoopError):
    """Template rendering or validation failed."""


class BrowserError(PromptLoopError):
    """Browser lifecycle failed."""


class ChatbotError(PromptLoopError):
    """Chatbot interaction failed."""


class ResultStoreError(PromptLoopError):
    """Saving a response failed."""


class StateError(PromptLoopError):
    """State (manifest) handling failed."""
