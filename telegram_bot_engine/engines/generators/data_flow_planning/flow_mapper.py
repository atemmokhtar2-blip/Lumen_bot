"""
FlowMapper — Specification 024

Discovers data sources/destinations, builds flow paths, transformations,
validation rules, security rules and error flows.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    DataSource, DataDestination, DataFlowPath, TransformationStep,
    ValidationRule, SecurityRule, ErrorFlow,
    SRC_USER_INPUT, SRC_TELEGRAM_UPDATE, SRC_CONFIG, SRC_ENV,
    SRC_EXTERNAL_API, SRC_DATABASE, SRC_CACHE,
    XFORM_CLEAN, XFORM_VALIDATE, XFORM_NORMALIZE, XFORM_ENCRYPT,
    SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL, SENSITIVITY_SENSITIVE, SENSITIVITY_SECRET,
)
from .data_readers import GenericData

_log = logging.getLogger("engine.data_flow_planning.flow_mapper")


class FlowMapper:
    def map(
        self,
        exec_data: GenericData,
        struct_data: GenericData,
        mod_data: GenericData,
        comp_data: GenericData,
        iface_data: GenericData,
        req_data: GenericData,
    ) -> Tuple[
        List[DataSource],
        List[DataDestination],
        List[DataFlowPath],
        List[ValidationRule],
        List[SecurityRule],
        List[ErrorFlow],
    ]:
        sources: List[DataSource] = []
        destinations: List[DataDestination] = []
        paths: List[DataFlowPath] = []
        validations: List[ValidationRule] = []
        security: List[SecurityRule] = []
        errors: List[ErrorFlow] = []

        # ------------------------------------------------------------------ #
        # Canonical sources
        # ------------------------------------------------------------------ #
        sources.extend([
            DataSource("src.telegram", "Telegram Updates", SRC_TELEGRAM_UPDATE,
                       "Incoming Telegram updates (messages, callbacks, commands)",
                       ["Update", "Message", "CallbackQuery"], SENSITIVITY_INTERNAL,
                       "mod.integration.telegram.adapter"),
            DataSource("src.user_input", "User Text Input", SRC_USER_INPUT,
                       "Free-text and structured user input extracted from updates",
                       ["str", "dict"], SENSITIVITY_INTERNAL,
                       "mod.core.handlers.controller"),
            DataSource("src.config", "Configuration", SRC_CONFIG,
                       "Application settings loaded from files / env",
                       ["Settings"], SENSITIVITY_SENSITIVE, "mod.infra.config"),
            DataSource("src.env", "Environment Variables", SRC_ENV,
                       "Runtime environment variables including secrets",
                       ["str"], SENSITIVITY_SECRET, "mod.infra.config"),
            DataSource("src.database", "Database", SRC_DATABASE,
                       "Persisted domain entities",
                       ["Entity"], SENSITIVITY_SENSITIVE,
                       "mod.infra.persistence.repository"),
            DataSource("src.cache", "Cache", SRC_CACHE,
                       "Short-lived cached values",
                       ["Any"], SENSITIVITY_INTERNAL, "mod.infra.persistence"),
            DataSource("src.external", "External APIs", SRC_EXTERNAL_API,
                       "Responses from third-party HTTP services",
                       ["dict", "bytes"], SENSITIVITY_INTERNAL,
                       "mod.integration.telegram.adapter"),
        ])

        # ------------------------------------------------------------------ #
        # Destinations
        # ------------------------------------------------------------------ #
        destinations.extend([
            DataDestination("dst.handlers", "Handler Layer",
                            "Updates arrive at controllers for routing",
                            "mod.core.handlers.controller", ["Update"]),
            DataDestination("dst.services", "Service Layer",
                            "Validated commands reach application services",
                            "mod.core.services.service", ["Command", "dict"]),
            DataDestination("dst.persistence", "Persistence Layer",
                            "Entities are saved / loaded",
                            "mod.infra.persistence.repository", ["Entity"]),
            DataDestination("dst.telegram_out", "Telegram Outbound",
                            "Messages sent back to users",
                            "mod.integration.telegram.adapter", ["OutboundMessage"]),
            DataDestination("dst.logs", "Logging Sink",
                            "Structured log records",
                            "mod.support.logging", ["LogRecord"]),
            DataDestination("dst.errors", "Error Handler",
                            "Domain and infrastructure errors",
                            "mod.core.services", ["Exception"]),
        ])

        # ------------------------------------------------------------------ #
        # Primary happy-path flows
        # ------------------------------------------------------------------ #
        paths.append(DataFlowPath(
            path_id="flow.telegram_to_handler",
            name="Telegram Update → Handler",
            source_id="src.telegram",
            destination_id="dst.handlers",
            steps=["mod.integration.telegram.adapter", "mod.core.handlers.controller"],
            transformations=[
                TransformationStep("t.validate_update", XFORM_VALIDATE,
                                   "Validate Update shape", "mod.core.handlers.validator",
                                   "Update", "Update"),
                TransformationStep("t.clean_text", XFORM_CLEAN,
                                   "Strip / normalise user text", "mod.core.handlers.controller",
                                   "str", "str"),
            ],
            sensitivity=SENSITIVITY_INTERNAL,
            description="Inbound Telegram updates are validated then dispatched to handlers",
        ))

        paths.append(DataFlowPath(
            path_id="flow.handler_to_service",
            name="Handler → Service",
            source_id="src.user_input",
            destination_id="dst.services",
            steps=["mod.core.handlers.controller", "mod.core.services.service"],
            transformations=[
                TransformationStep("t.normalize_cmd", XFORM_NORMALIZE,
                                   "Map update to application command",
                                   "mod.core.handlers.controller", "Update", "Command"),
            ],
            sensitivity=SENSITIVITY_INTERNAL,
            description="Handlers translate updates into domain commands for services",
        ))

        paths.append(DataFlowPath(
            path_id="flow.service_to_db",
            name="Service → Persistence",
            source_id="src.user_input",
            destination_id="dst.persistence",
            steps=["mod.core.services.service", "mod.infra.persistence.repository"],
            transformations=[
                TransformationStep("t.to_entity", XFORM_NORMALIZE,
                                   "Map command data to domain entity",
                                   "mod.core.services.service", "Command", "Entity"),
            ],
            sensitivity=SENSITIVITY_SENSITIVE,
            description="Services persist domain entities via repositories",
        ))

        paths.append(DataFlowPath(
            path_id="flow.service_to_telegram",
            name="Service → Telegram Outbound",
            source_id="src.user_input",
            destination_id="dst.telegram_out",
            steps=["mod.core.services.service", "mod.integration.telegram.adapter"],
            transformations=[],
            sensitivity=SENSITIVITY_INTERNAL,
            description="Service results are rendered and sent back to the user",
        ))

        paths.append(DataFlowPath(
            path_id="flow.config_bootstrap",
            name="Config / Env → Runtime",
            source_id="src.config",
            destination_id="dst.services",
            steps=["mod.infra.config", "mod.core.services.service"],
            transformations=[
                TransformationStep("t.load_settings", XFORM_NORMALIZE,
                                   "Load and validate settings", "mod.infra.config",
                                   "dict", "Settings"),
            ],
            sensitivity=SENSITIVITY_SENSITIVE,
            description="Configuration is loaded once at bootstrap and injected",
        ))

        paths.append(DataFlowPath(
            path_id="flow.secrets",
            name="Secrets (Env) → Config",
            source_id="src.env",
            destination_id="dst.services",
            steps=["mod.infra.config"],
            transformations=[
                TransformationStep("t.mask_secrets", XFORM_ENCRYPT,
                                   "Keep secrets in memory only, never log",
                                   "mod.infra.config", "str", "SecretStr"),
            ],
            sensitivity=SENSITIVITY_SECRET,
            description="Environment secrets flow only into the config module",
        ))

        # ------------------------------------------------------------------ #
        # Validation rules
        # ------------------------------------------------------------------ #
        validations.extend([
            ValidationRule("val.update_shape", "Telegram Update must contain update_id",
                           "src.telegram", "completeness"),
            ValidationRule("val.cmd_type", "Command type must be registered",
                           "flow.handler_to_service", "type"),
            ValidationRule("val.entity_id", "Entity must have a non-empty id before save",
                           "flow.service_to_db", "completeness"),
            ValidationRule("val.settings", "Required settings keys must be present",
                           "src.config", "completeness"),
        ])

        # ------------------------------------------------------------------ #
        # Security rules
        # ------------------------------------------------------------------ #
        security.extend([
            SecurityRule("sec.secrets_never_log",
                         "Secret values from env must never appear in logs",
                         SENSITIVITY_SECRET, "mask",
                         ["src.env", "flow.secrets"]),
            SecurityRule("sec.db_restricted",
                         "Only persistence module may read/write the database",
                         SENSITIVITY_SENSITIVE, "restrict",
                         ["src.database", "dst.persistence"]),
            SecurityRule("sec.no_raw_update_to_db",
                         "Raw Telegram updates must not be stored untransformed",
                         SENSITIVITY_SENSITIVE, "restrict",
                         ["src.telegram", "dst.persistence"]),
            SecurityRule("sec.encrypt_tokens",
                         "Bot tokens and API keys must be treated as secrets",
                         SENSITIVITY_SECRET, "encrypt",
                         ["src.env", "src.config"]),
        ])

        # ------------------------------------------------------------------ #
        # Error flows
        # ------------------------------------------------------------------ #
        errors.extend([
            ErrorFlow("err.validation", "Validation Error",
                      "flow.telegram_to_handler", "mod.core.handlers.controller",
                      "stop", "Invalid updates are rejected; user receives a friendly message"),
            ErrorFlow("err.domain", "Domain Error",
                      "flow.handler_to_service", "mod.core.services.service",
                      "convert", "Domain errors are converted to user-visible replies"),
            ErrorFlow("err.persistence", "Persistence Error",
                      "flow.service_to_db", "mod.infra.persistence.repository",
                      "bubble", "DB errors bubble to the service which decides retry/fail"),
            ErrorFlow("err.external", "External API Error",
                      "flow.service_to_telegram", "mod.integration.telegram.adapter",
                      "convert", "Network/API errors are logged and a fallback reply is sent"),
        ])

        _log.info(
            "FlowMapper: %d sources, %d destinations, %d paths, %d security rules",
            len(sources), len(destinations), len(paths), len(security),
        )
        return sources, destinations, paths, validations, security, errors


__all__ = ["FlowMapper"]
