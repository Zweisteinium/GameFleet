from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from gamefleet_backend.models.game_server_type import GameServerType
from gamefleet_backend.services.game_asset_service import get_asset_path, ASSET_KINDS

router = APIRouter()


@router.get("/{game}/{kind}", operation_id="getGameAsset", response_class=FileResponse)
async def get_game_asset(game: GameServerType, kind: str):
    """Serve cached game artwork: `poster` (portrait) or `hero` (wide banner)."""
    if kind not in ASSET_KINDS:
        raise HTTPException(status_code=404, detail="Unknown asset kind")
    path = await get_asset_path(game, kind)
    if path is None:
        raise HTTPException(status_code=404, detail="No artwork available for this game")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800, immutable"})
