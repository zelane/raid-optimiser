"""
teams - finding a team by what its champions bring: buffs, debuffs, skill effects and
mechanics, from their skills and from gear (sets, relics) or what the user assumes, each rated
for how far it can be counted on. A team is asked for `Goals`: objectives, each needs met
against a `Target` (an enemy and its immunities) and maybe waiting on another, and extras
every team must bring. The search finds every smallest team meeting them all, or the few
meeting the most. Damage, turn order and ACC against RES aren't modelled.

What can be brought and its names, and the target, are `tags`; what a team must bring,
`needs`; what a champion brings, `kits`; sets, relics and assumptions, `gear`; who in a team
covers what and its score, `cover`; finding teams, `search`. `optimiser.chimera` asks it for
the Chimera's trials. Builds on `optimiser.account`.
"""
