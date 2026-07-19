"""
OpenTelemetry Instrumentation Utility
Provides easy setup for distributed tracing in Python services
"""
import os
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

def setup_tracing(service_name: str, service_version: str = "1.0.0"):
    """
    Setup OpenTelemetry tracing for a service
    
    Usage:
        from otel_setup import setup_tracing
        setup_tracing("ledgerline-dispatcher")
    """
    # Create resource with service information
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": os.getenv("ENVIRONMENT", "development")
    })
    
    # Create tracer provider
    provider = TracerProvider(resource=resource)
    
    # Configure OTLP exporter
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    
    # Add span processor
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    
    # Set as global tracer provider
    trace.set_tracer_provider(provider)
    
    # Auto-instrument libraries
    RequestsInstrumentor().instrument()
    Psycopg2Instrumentor().instrument()
    RedisInstrumentor().instrument()
    
    return trace.get_tracer(service_name)

def instrument_fastapi(app, service_name: str):
    """
    Instrument FastAPI application
    
    Usage:
        from otel_setup import instrument_fastapi
        app = FastAPI()
        instrument_fastapi(app, "ledgerline-dispatcher")
    """
    FastAPIInstrumentor.instrument_app(app, tracer_provider=trace.get_tracer_provider())
