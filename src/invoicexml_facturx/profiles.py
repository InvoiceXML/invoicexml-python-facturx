"""Specification identifiers of the official Factur-X profiles."""

from __future__ import annotations


class FacturXProfile:
    """Set one as the invoice's ``specification_id`` to select that profile on
    create. Without one, the API creates the EN 16931 profile."""

    MINIMUM = "urn:factur-x.eu:1p0:minimum"
    """MINIMUM: header data only, a booking aid rather than a full e-invoice."""
    BASIC_WL = "urn:factur-x.eu:1p0:basicwl"
    """BASIC WL: header and totals without lines, a booking aid rather than a full e-invoice."""
    BASIC = "urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic"
    """BASIC: a subset of EN 16931 with line items. The lowest profile the French mandate accepts."""
    EN16931 = "urn:cen.eu:en16931:2017"
    """EN 16931: the European standard invoice, the default and recommended profile."""
    EXTENDED = "urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended"
    """EXTENDED: EN 16931 plus additional business data for complex invoicing."""
