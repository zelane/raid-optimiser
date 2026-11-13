//! Champions: `UserWrapper.Heroes.HeroData.HeroById`.
//!
//! - `Hero`: what the optimiser uses of one (static facts come from the game's tables)
//! - `read`: every champion

use std::collections::BTreeMap;

use serde::Serialize;

use crate::collections::{dict_refs, list_i32, list_refs};
use crate::layout::{offsets, Layout};
use crate::process::Process;

const PATH: [&str; 3] = [
    "UserWrapper.Heroes",
    "HeroesWrapperReadOnly.HeroData",
    "UserHeroData.HeroById",
];

offsets!(HeroFields, "Hero" {
    id: "Id", type_id: "TypeId", grade: "Grade", level: "Level", empower: "EmpowerLevel",
    skills: "Skills", mastery: "MasteryData", double_ascend: "DoubleAscendData",
});
offsets!(SkillFields, "Skill" { type_id: "TypeId", level: "Level" });

#[derive(Serialize)]
pub struct Hero {
    pub id: i32,
    pub type_id: i32,
    pub grade: i32,
    pub level: i32,
    pub empower: i32,
    /// `DoubleAscendGrade` (0: not awakened)
    pub awakened_grade: i32,
    /// skill type id → level
    pub skills: BTreeMap<i32, i32>,
    pub masteries: Vec<i32>,
}

pub fn read(process: &Process, layout: &Layout, user: u64) -> Result<Vec<Hero>, String> {
    let hero = HeroFields::new(layout)?;
    let skill = SkillFields::new(layout)?;
    let masteries = layout.field("HeroMasteryData.Masteries")?;
    let awakened = layout.field("HeroDoubleAscendData.Grade")?;
    let by_id = layout.follow(process, user, &PATH)?;

    dict_refs(process, by_id)?
        .into_iter()
        .map(|(_, addr)| {
            let b = process.block(addr, hero.span)?;
            let skills = list_refs(process, b.ptr(hero.skills))?
                .into_iter()
                .map(|s| {
                    Ok((
                        process.read(s + skill.type_id)?,
                        process.read(s + skill.level)?,
                    ))
                })
                .collect::<Result<_, String>>()?;
            let masteries = match b.ptr(hero.mastery) {
                0 => Vec::new(),
                data => list_i32(process, process.read(data + masteries)?)?,
            };
            let awakened_grade = match b.ptr(hero.double_ascend) {
                0 => 0,
                data => process.read(data + awakened)?,
            };

            Ok(Hero {
                id: b.i32(hero.id),
                type_id: b.i32(hero.type_id),
                grade: b.i32(hero.grade),
                level: b.i32(hero.level),
                empower: b.i32(hero.empower),
                awakened_grade,
                skills,
                masteries,
            })
        })
        .collect()
}
