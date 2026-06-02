from app.models import GatewayEvent


def make_handler(connection_string: str):
    if not connection_string:

        async def noop(event: GatewayEvent) -> None:
            pass

        return noop

    from opencensus.ext.azure import metrics_exporter
    from opencensus.stats import aggregation, measure, stats, view

    # Registers itself with the global view manager; no local reference needed.
    metrics_exporter.new_metrics_exporter(connection_string=connection_string)

    m_latency = measure.MeasureFloat("gateway/latency_ms", "Request latency", "ms")
    m_tokens = measure.MeasureInt("gateway/tokens", "Total tokens", "tokens")
    latency_view = view.View(
        "gateway/latency_ms", "", [], m_latency, aggregation.LastValueAggregation()
    )
    token_view = view.View("gateway/tokens", "", [], m_tokens, aggregation.SumAggregation())
    stats.stats.view_manager.register_view(latency_view)
    stats.stats.view_manager.register_view(token_view)

    async def handle(event: GatewayEvent) -> None:
        mmap = stats.stats.stats_recorder.new_measurement_map()
        if event.latency_ms is not None:
            mmap.measure_float_put(m_latency, float(event.latency_ms))
        mmap.measure_int_put(m_tokens, event.tokens_input + event.tokens_output)
        mmap.record()

    return handle
