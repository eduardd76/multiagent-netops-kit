"""The one dispatcher every audit hook uses (its own module to avoid import cycles)."""


def emit(sink, event) -> None:
    """Call a sink: record_event() if it has one (MockServiceNowIncident keeps data in .record), else record()."""
    (getattr(sink, "record_event", None) or sink.record)(event)
