from __future__ import annotations

from typing import Protocol, runtime_checkable

from sfa.domain.ports import CompetitionDTO, CompetitionRepositoryProtocol


@runtime_checkable
class ListCompetitionsUseCaseProtocol(Protocol):
    async def execute(self) -> list[CompetitionDTO]: ...


class ListCompetitionsUseCase(ListCompetitionsUseCaseProtocol):
    def __init__(self, comp_repo: CompetitionRepositoryProtocol) -> None:
        self._comp_repo = comp_repo

    async def execute(self) -> list[CompetitionDTO]:
        return await self._comp_repo.get_all()
