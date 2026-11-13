"""
chimera - the Chimera trial team builder: one team that clears a column of trials (Wing, Tail
or Paw: Easy, then Normal, then Hard) in all three of the Chimera's animal forms in a single
Ultra Nightmare fight, the column holding this rotation's mythical materials. Rewards only
count for trials cleared in the same fight, and each Normal or Hard trial only starts once the
one above it is done. The user puts the champions they want in the team's slots; the search
fills the open ones.

A team qualifies on what its champions can place and do (skills, and the sets, relics and
assumptions the user allows), against what each trial's rules check and each form's
immunities, and is scored on how far it can count on them. Damage isn't modelled (a trial's
target is shown, not checked), nor turn order, nor who holds a buff when it counts, nor ACC
against the Chimera's RES.

What can be brought, the Chimera's immunities and their names are `tags`; the trials and what
each needs, `trials`; what a champion brings and how far it can be counted on, `kits`; sets,
relics and assumptions, `gear`; who in a team covers what and its score, `cover`; finding
teams, `search`; the entry points, `plan`. Builds on `optimiser.account` and
`optimiser.enemies` (the trials); the gear solver doesn't come into it.
"""
