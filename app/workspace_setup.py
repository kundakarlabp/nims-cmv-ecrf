"""Fixed host-only sequence initialization after the owner-confirmed reset."""
from sqlalchemy import select
from .main import SessionLocal, User, AuthContext
from .trial_models import RandomizationPlan
from .workspace_policy import enabled
from .randomization import GenerateSequence, generate_and_lock

def initialize():
    if not enabled():raise RuntimeError('Owner team-workspace authorization required')
    with SessionLocal() as s:
        if s.scalar(select(RandomizationPlan.id).limit(1)) is not None:
            return {'sequence_ready':True,'created':False}
        owners=s.scalars(select(User).where(User.active.is_(True),User.pi_authorized.is_(True))).all()
        if len(owners)!=1:raise RuntimeError('A unique authorized owner account is required')
        owner=owners[0]
        actor=AuthContext(user_id=owner.id,role=owner.role,name=owner.display_name,
            csrf_hash='',pi_authorized=True,workspace_full_access=True)
        generate_and_lock(GenerateSequence(
            statistician_reference='Owner-managed automated allocation; independent custodian removed by owner',
            signed_specification_reference='Owner instruction 18 November 2026; four v5 strata and 1:1 variable blocks retained',
            independent_sequence_attested=False,block_sizes=[4,6,8]),actor,s)
    return {'sequence_ready':True,'created':True}

if __name__=='__main__':
    initialize()
    print('Owner-managed concealed sequence ready. No future assignments disclosed.')
