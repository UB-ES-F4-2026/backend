"""Estat de finançament d'una oportunitat en un moment donat.

És l'estat que es mostra a l'usuari: es calcula a partir de l'estat editorial
de l'oportunitat, el capital compromès i el termini, i no es desa enlloc.
"""
from datetime import datetime
from enum import Enum

from app.models.opportunity import Opportunity, OpportunityStatus


class FundingStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    CLOSED = "closed"
    FUNDED = "funded"
    EXPIRED = "expired"
    IN_FUNDING = "in_funding"


def funding_status(opportunity: Opportunity, now: datetime) -> FundingStatus:
    """Retorna l'estat de finançament de l'oportunitat a l'instant `now`.

    L'ordre de les comprovacions és la prioritat entre estats:

    1. Un esborrany està pendent de revisió i una rebutjada és rebutjada,
       tinguin el capital i el termini que tinguin: no han estat mai en
       finançament.
    2. Un tancament anticipat preval sobre l'objectiu i el termini.
    3. Assolir l'objectiu preval sobre el termini: una oportunitat finançada
       ho continua sent quan passa la data límit. El termini només compta
       com a finalitzat si ha passat sense assolir l'objectiu.
    """
    if opportunity.status == OpportunityStatus.DRAFT:
        return FundingStatus.PENDING_REVIEW
    if opportunity.status == OpportunityStatus.REJECTED:
        return FundingStatus.REJECTED
    if opportunity.status == OpportunityStatus.CLOSED or opportunity.date_closed is not None:
        return FundingStatus.CLOSED
    if opportunity.committed_cents >= opportunity.target_amount_cents:
        return FundingStatus.FUNDED
    if opportunity.deadline <= now:
        return FundingStatus.EXPIRED
    return FundingStatus.IN_FUNDING
