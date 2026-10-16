"""
CQRS Pattern: Command & Query Handlers

Implements dedicated handlers for executing state-changing commands and read-only queries,
strictly separating domain write operations from read representations.
"""

from typing import Any, Dict, List, Optional
from tripmate.cqrs.commands import (
    CreateAlertCommand,
    CreateAssetCommand,
    CreateWatchlistCommand,
    DeleteAlertCommand,
    DeleteAssetCommand,
    DeleteWatchlistCommand,
    MarkAlertReadCommand,
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
from tripmate.repositories.interfaces import (
    IAlertRepository,
    IAssetRepository,
    IWatchlistRepository,
)
from tripmate.repositories.store_repositories import (
    alert_repository,
    asset_repository,
    watchlist_repository,
)


class WatchlistCommandHandlers:
    """Handles state mutations for travel watchlists."""

    def __init__(self, repo: IWatchlistRepository = watchlist_repository):
        self._repo = repo

    def handle_create(self, cmd: CreateWatchlistCommand) -> Dict[str, Any]:
        return self._repo.create(
            user_id=cmd.user_id,
            title=cmd.title,
            target_type=cmd.target_type,
            target_value=cmd.target_value,
            threshold_price=cmd.threshold_price,
            notes=cmd.notes,
        )

    def handle_delete(self, cmd: DeleteWatchlistCommand) -> bool:
        return self._repo.delete(cmd.item_id, cmd.user_id)


class WatchlistQueryHandlers:
    """Handles read operations for travel watchlists (zero side effects)."""

    def __init__(self, repo: IWatchlistRepository = watchlist_repository):
        self._repo = repo

    def handle_get(self, query: GetWatchlistQuery) -> Optional[Dict[str, Any]]:
        return self._repo.get_by_id(query.item_id, query.user_id)

    def handle_list(self, query: ListWatchlistsQuery) -> List[Dict[str, Any]]:
        return self._repo.list_by_user(query.user_id)


class AlertCommandHandlers:
    """Handles state mutations for notification alerts."""

    def __init__(self, repo: IAlertRepository = alert_repository):
        self._repo = repo

    def handle_create(self, cmd: CreateAlertCommand) -> Dict[str, Any]:
        return self._repo.create(
            user_id=cmd.user_id,
            title=cmd.title,
            message=cmd.message,
            alert_type=cmd.alert_type,
            severity=cmd.severity,
            watchlist_id=cmd.watchlist_id,
        )

    def handle_mark_read(self, cmd: MarkAlertReadCommand) -> Optional[Dict[str, Any]]:
        return self._repo.mark_as_read(cmd.alert_id, cmd.user_id)

    def handle_delete(self, cmd: DeleteAlertCommand) -> bool:
        return self._repo.delete(cmd.alert_id, cmd.user_id)


class AlertQueryHandlers:
    """Handles read operations for alerts (zero side effects)."""

    def __init__(self, repo: IAlertRepository = alert_repository):
        self._repo = repo

    def handle_list(self, query: ListAlertsQuery) -> List[Dict[str, Any]]:
        return self._repo.list_by_user(query.user_id)


class AssetCommandHandlers:
    """Handles state mutations for travel assets and documents."""

    def __init__(self, repo: IAssetRepository = asset_repository):
        self._repo = repo

    def handle_create(self, cmd: CreateAssetCommand) -> Dict[str, Any]:
        return self._repo.create(
            user_id=cmd.user_id,
            name=cmd.name,
            asset_type=cmd.asset_type,
            trip_id=cmd.trip_id,
            content_uri=cmd.content_uri,
            metadata=cmd.metadata,
        )

    def handle_delete(self, cmd: DeleteAssetCommand) -> bool:
        return self._repo.delete(cmd.asset_id, cmd.user_id)


class AssetQueryHandlers:
    """Handles read operations for travel assets (zero side effects)."""

    def __init__(self, repo: IAssetRepository = asset_repository):
        self._repo = repo

    def handle_get(self, query: GetAssetQuery) -> Optional[Dict[str, Any]]:
        return self._repo.get_by_id(query.asset_id, query.user_id)

    def handle_list(self, query: ListAssetsQuery) -> List[Dict[str, Any]]:
        return self._repo.list_by_user(query.user_id, query.trip_id)


class RunQueryHandlers:
    """Handles read operations for workflow execution telemetry."""

    def __init__(self, run_store: Optional[Dict[str, Dict[str, Any]]] = None):
        self._store = run_store

    @property
    def store(self):
        if self._store is None:
            from tripmate.services.travel_service import RUN_STORE
            self._store = RUN_STORE
        return self._store

    def handle_get_details(self, query: GetRunDetailsQuery) -> Optional[Dict[str, Any]]:
        return self.store.get(query.run_id)

    def handle_get_metrics(self, query: GetRunMetricsQuery) -> Optional[Dict[str, Any]]:
        record = self.store.get(query.run_id)
        if not record:
            return None
        return record.get("metrics")
