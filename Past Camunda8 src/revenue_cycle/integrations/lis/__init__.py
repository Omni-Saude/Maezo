"""LIS (Laboratory Information System) integration."""

from revenue_cycle.integrations.lis.client import LISClient
from revenue_cycle.integrations.lis.models import LISOrderDTO, LISResultDTO

__all__ = ["LISClient", "LISOrderDTO", "LISResultDTO"]
