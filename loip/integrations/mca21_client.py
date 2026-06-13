"""MCA21 employer CIN verification API client (Phase 2).

Verifies employer Corporate Identity Number (CIN) against the Ministry
of Corporate Affairs database. Used to detect shell company employers
(fraud signal: employer_shell).
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import BaseClient, IntegrationError


@dataclass
class CompanyInfo:
    cin: str
    company_name: str
    status: str  # "active", "struck_off", "dormant", "not_found"
    date_of_incorporation: str | None
    registered_address: str | None
    authorized_capital: float | None
    paid_up_capital: float | None
    company_class: str | None  # "private", "public", "opc"
    is_listed: bool
    mock: bool = False


class MCA21Client(BaseClient):
    service_name = "mca21"
    env_prefix = "MCA21"

    async def verify_cin(self, cin: str) -> CompanyInfo:
        """Verify a Corporate Identity Number against MCA21 database.

        Args:
            cin: 21-character CIN (e.g. U72200KA2009PTC049889)
        """
        if len(cin) != 21:
            return CompanyInfo(
                cin=cin,
                company_name="",
                status="format_invalid",
                date_of_incorporation=None,
                registered_address=None,
                authorized_capital=None,
                paid_up_capital=None,
                company_class=None,
                is_listed=False,
            )

        if self._mock:
            return self._mock_response(cin)

        try:
            data = await self._request("GET", f"company/{cin}")
        except IntegrationError:
            raise

        return CompanyInfo(
            cin=cin,
            company_name=data.get("company_name", ""),
            status=data.get("status", "unknown"),
            date_of_incorporation=data.get("date_of_incorporation"),
            registered_address=data.get("registered_address"),
            authorized_capital=data.get("authorized_capital"),
            paid_up_capital=data.get("paid_up_capital"),
            company_class=data.get("company_class"),
            is_listed=data.get("is_listed", False),
        )

    async def search_company(self, name: str) -> list[CompanyInfo]:
        """Search for companies by name."""
        if self._mock:
            return [self._mock_response("U72200KA2009PTC049889")]

        try:
            data = await self._request("GET", "search", params={"name": name})
        except IntegrationError:
            raise

        return [
            CompanyInfo(
                cin=item["cin"],
                company_name=item.get("company_name", ""),
                status=item.get("status", "unknown"),
                date_of_incorporation=item.get("date_of_incorporation"),
                registered_address=item.get("registered_address"),
                authorized_capital=item.get("authorized_capital"),
                paid_up_capital=item.get("paid_up_capital"),
                company_class=item.get("company_class"),
                is_listed=item.get("is_listed", False),
            )
            for item in data.get("results", [])
        ]

    def _mock_response(self, cin: str) -> CompanyInfo:
        return CompanyInfo(
            cin=cin,
            company_name="Mock Technologies Pvt Ltd",
            status="active",
            date_of_incorporation="15/06/2009",
            registered_address="No. 42, Electronic City, Bengaluru, Karnataka 560100",
            authorized_capital=10000000.0,
            paid_up_capital=5000000.0,
            company_class="private",
            is_listed=False,
            mock=True,
        )
