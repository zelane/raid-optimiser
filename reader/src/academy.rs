//! The Academy's guardians: `UserWrapper.Academy` → `AcademyData.Guardians`. Champions placed
//! as guardians raise every champion of their faction and rarity (the game's
//! `AcademySetup.Create` turns them into a champion's bonus in battle, for the battle host).
//!
//! - `Slot`: one guardian slot (up to two champions, by id)
//! - `Guardians`: faction → rarity → its slots, by the game's names
//! - `read`: them (none if the Academy isn't loaded)

use std::collections::BTreeMap;

use serde::Serialize;

use crate::collections::{dict_refs, list_refs};
use crate::layout::{offsets, Layout};
use crate::process::Process;

const PATH: [&str; 3] = [
    "UserWrapper.Academy",
    "AcademyWrapperReadOnly.AcademyData",
    "UserAcademyData.Guardians",
];

offsets!(SlotFields, "AcademyGuardiansSlot" {
    first: "FirstHero", second: "SecondHero", consumed: "Consumed", base_type: "HeroBaseTypeId",
});

#[derive(Serialize)]
pub struct Slot {
    pub first_hero: Option<i32>,
    pub second_hero: Option<i32>,
    pub consumed: Option<bool>,
    pub hero_base_type_id: Option<i32>,
}

pub type Guardians = BTreeMap<String, BTreeMap<String, Vec<Slot>>>;

pub fn read(process: &Process, layout: &Layout, user: u64) -> Result<Guardians, String> {
    let slot = SlotFields::new(layout)?;
    let by_fraction = layout.field("UserAcademyGuardiansData.SlotsByFraction")?;
    let by_rarity = layout.field("AcademyGuardiansRaritySlots.SlotsByRarity")?;
    let guardians = layout.follow(process, user, &PATH)?;

    dict_refs(process, process.read(guardians + by_fraction)?)?
        .into_iter()
        .map(|(fraction, rarities)| {
            let slots = dict_refs(process, process.read(rarities + by_rarity)?)?
                .into_iter()
                .map(|(rarity, list)| {
                    let slots = list_refs(process, list)?
                        .into_iter()
                        .filter(|&s| s != 0)
                        .map(|s| {
                            let b = process.block(s, slot.span)?;
                            Ok(Slot {
                                first_hero: b.nullable_i32(slot.first),
                                second_hero: b.nullable_i32(slot.second),
                                consumed: b.nullable_bool(slot.consumed),
                                hero_base_type_id: b.nullable_i32(slot.base_type),
                            })
                        })
                        .collect::<Result<_, String>>()?;
                    Ok((layout.name("HeroRarity", rarity)?, slots))
                })
                .collect::<Result<_, String>>()?;
            Ok((layout.name("HeroFraction", fraction)?, slots))
        })
        .collect()
}
