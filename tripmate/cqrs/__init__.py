"""
CQRS Pattern Module

Exposes commands, queries, handlers, and dispatch buses.
"""

from tripmate.cqrs.commands import (
    CreateAlertCommand,
    CreateAssetCommand,
    CreateWatchlistCommand,
    DeleteAlertCommand,
    DeleteAssetCommand,
    DeleteWatchlistCommand,
    ExecuteTravelPlanCommand,
    MarkAlertReadCommand,
    ResumeTravelPlanCommand,
)
from tripmate.cqrs.queries import (
    GetAssetQuery,
    GetRunDetailsQuery,
    GetRunMetricsQuery,
    GetWatchlistQuery,
    ListAlertsQuery,
    ListAssetsQuery,
    ListWatchlistsQuery,
)
from tripmate.cqrs.handlers import (
    AlertCommandHandlers,
    AlertQueryHandlers,
    AssetCommandHandlers,
    AssetQueryHandlers,
    RunQueryHandlers,
    WatchlistCommandHandlers,
    WatchlistQueryHandlers,
)
from tripmate.cqrs.bus import CommandBus, QueryBus, command_bus, query_bus

__all__ = [
    "CreateWatchlistCommand",
    "DeleteWatchlistCommand",
    "CreateAlertCommand",
    "MarkAlertReadCommand",
    "DeleteAlertCommand",
    "CreateAssetCommand",
    "DeleteAssetCommand",
    "ExecuteTravelPlanCommand",
    "ResumeTravelPlanCommand",
    "GetWatchlistQuery",
    "ListWatchlistsQuery",
    "ListAlertsQuery",
    "GetAssetQuery",
    "ListAssetsQuery",
    "GetRunDetailsQuery",
    "GetRunMetricsQuery",
    "WatchlistCommandHandlers",
    "WatchlistQueryHandlers",
    "AlertCommandHandlers",
    "AlertQueryHandlers",
    "AssetCommandHandlers",
    "AssetQueryHandlers",
    "RunQueryHandlers",
    "CommandBus",
    "QueryBus",
    "command_bus",
    "query_bus",
]
