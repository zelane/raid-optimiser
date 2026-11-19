//! Gear: `UserWrapper.Artifacts.ArtifactData` (who wears what) and the artifact storage.
//!
//! - `Artifact`, `Bonus`: a piece and its stat lines (enums by the game's names)
//! - `Reader`: reads pieces (also the inbox's, `account`)
//! - `read`: every piece the account holds, and where they were read from
//! - `equipped`: champion id → the ids of the pieces they wear
//! - `GearPreset`, `presets`: saved gear presets (a champion's, or global), from the storage

use std::collections::BTreeMap;

use serde::Serialize;

use crate::collections::{dict_i32, dict_refs, list_i32, list_refs, string};
use crate::layout::{offsets, Layout};
use crate::process::Process;
use crate::roots;

const DATA: [&str; 2] = [
    "UserWrapper.Artifacts",
    "EquipmentWrapperReadonly.ArtifactData",
];
/// The storage the game moves pieces into (`ArtifactStorageMigrationState.Migrated`); the
/// account's own list is used otherwise.
const EXTERNAL: &str = "Client.Model.Gameplay.Artifacts.ExternalArtifactsStorage";
const CACHE: [&str; 2] = [
    "ExternalArtifactsStorage._cachedArtifacts",
    "CachedArtifacts._artifacts",
];

offsets!(ArtifactFields, "Artifact" {
    id: "_id", level: "_level", ascend_level: "_ascendLevel", kind: "_kindId",
    variant: "_variantId", rank: "_rankId", rarity: "_rarityId", primary: "_primaryBonus",
    substats: "_secondaryBonuses", ascend: "_ascendBonus", set: "_setKindId",
    faction: "_requiredFraction", rerolls: "_rerollsCount",
});
offsets!(BonusFields, "ArtifactBonus" {
    stat: "_kindId", value: "_value", glyph: "_powerUpValue", rolls: "_level",
});
const PRESETS: [&str; 2] = [
    "ExternalArtifactsStorage._presets",
    "ArtifactPresets._presets",
];
/// The key the game keeps global presets under (`GlobalGroupHeroId`)
const GLOBAL: i32 = -1;

offsets!(PresetsOfTypeFields, "ArtifactsPresetsOfType" {
    artifacts: "_artifactPresets", accessories: "_accessoryPresets",
});
offsets!(PresetFields, "ArtifactPreset" { id: "_id", name: "_name", ids: "_artifactIds" });
offsets!(ValueFields, "BonusValue" { absolute: "_isAbsolute", value: "_value" });

#[derive(Serialize)]
pub struct Bonus {
    pub stat: String,
    pub absolute: bool,
    pub value: f64,
    pub glyph: f64,
    pub rolls: i32,
}

#[derive(Serialize)]
pub struct Artifact {
    pub id: i32,
    pub kind: String,
    pub set: i32,
    pub rank: i32,
    pub rarity: String,
    pub level: i32,
    pub faction: String,
    pub variant: String,
    pub rerolls: Option<i32>,
    pub ascend_level: Option<i32>,
    pub primary: Bonus,
    pub substats: Vec<Bonus>,
    pub ascend: Option<Bonus>,
}

pub struct Reader<'a> {
    layout: &'a Layout,
    artifact: ArtifactFields,
    bonus: BonusFields,
    value: ValueFields,
}

impl<'a> Reader<'a> {
    pub fn new(layout: &'a Layout) -> Result<Reader<'a>, String> {
        Ok(Reader {
            layout,
            artifact: ArtifactFields::new(layout)?,
            bonus: BonusFields::new(layout)?,
            value: ValueFields::new(layout)?,
        })
    }

    pub fn artifact(&self, process: &Process, addr: u64) -> Result<Artifact, String> {
        let f = &self.artifact;
        let b = process.block(addr, f.span)?;
        let substats = list_refs(process, b.ptr(f.substats))?
            .into_iter()
            .map(|line| self.bonus(process, line))
            .collect::<Result<_, String>>()?;
        let ascend = match b.ptr(f.ascend) {
            0 => None,
            line => Some(self.bonus(process, line)?),
        };

        Ok(Artifact {
            id: b.i32(f.id),
            kind: self.layout.name("ArtifactKindId", b.i32(f.kind))?,
            set: b.i32(f.set),
            rank: b.i32(f.rank),
            rarity: self.layout.name("ItemRarity", b.i32(f.rarity))?,
            level: b.i32(f.level),
            faction: self.layout.name("HeroFraction", b.i32(f.faction))?,
            variant: self.layout.name("ArtifactVariantId", b.i32(f.variant))?,
            rerolls: b.nullable_i32(f.rerolls),
            ascend_level: b.nullable_i32(f.ascend_level),
            primary: self.bonus(process, process.ptr(addr + f.primary, "primary bonus")?)?,
            substats,
            ascend,
        })
    }

    fn bonus(&self, process: &Process, addr: u64) -> Result<Bonus, String> {
        let b = process.block(addr, self.bonus.span)?;
        let v = process.block(
            process.ptr(addr + self.bonus.value, "bonus value")?,
            self.value.span,
        )?;

        Ok(Bonus {
            stat: self.layout.name("StatKindId", b.i32(self.bonus.stat))?,
            absolute: v.bool(self.value.absolute),
            value: v.fixed(self.value.value),
            glyph: b.fixed(self.bonus.glyph),
            rolls: b.i32(self.bonus.rolls),
        })
    }
}

/// Every piece, from the external storage when the game uses it, else the account's list.
pub fn read(
    process: &Process,
    layout: &Layout,
    reader: &Reader,
    user: u64,
) -> Result<(Vec<Artifact>, String), String> {
    let (storage, class) = roots::artifact_storage(process, layout)?;
    let data = layout.follow(process, user, &DATA)?;
    let list = list_refs(
        process,
        process.read(data + layout.field("UserArtifactData.Artifacts")?)?,
    )?;
    let (addrs, source) = match class == EXTERNAL {
        true => {
            let cache = layout.follow(process, storage, &CACHE)?;
            // pieces gone since (sold, used) stay in the cache as null (11.95.0)
            let addrs: Vec<u64> = dict_refs(process, cache)?
                .into_iter()
                .map(|(_, a)| a)
                .filter(|&a| a != 0)
                .collect();
            let source = format!("external storage ({} in the account's list)", list.len());
            (addrs, source)
        }
        false => (list, format!("the account's list (storage: {class})")),
    };

    let artifacts = addrs
        .into_iter()
        .map(|a| reader.artifact(process, a))
        .collect::<Result<_, _>>()?;
    Ok((artifacts, source))
}

pub fn equipped(
    process: &Process,
    layout: &Layout,
    user: u64,
) -> Result<BTreeMap<i32, Vec<i32>>, String> {
    let data = layout.follow(process, user, &DATA)?;
    let by_hero = process.read(data + layout.field("UserArtifactData.ArtifactDataByHeroId")?)?;
    let by_kind = layout.field("HeroArtifactData.ArtifactIdByKind")?;

    dict_refs(process, by_hero)?
        .into_iter()
        .map(|(hero, data)| {
            let pieces = dict_i32(process, process.read(data + by_kind)?)?;
            Ok((hero, pieces.into_iter().map(|(_, id)| id).collect()))
        })
        .collect()
}

#[derive(Serialize)]
pub struct GearPreset {
    pub id: i64,
    /// the champion it belongs to; None for a global preset
    pub hero_id: Option<i32>,
    pub name: String,
    /// an accessory preset (ring, amulet, banner) rather than an artifact one
    pub accessories: bool,
    pub artifact_ids: Vec<i32>,
}

/// Every saved gear preset; none when the game doesn't use the external storage.
pub fn presets(process: &Process, layout: &Layout) -> Result<Vec<GearPreset>, String> {
    let (storage, class) = roots::artifact_storage(process, layout)?;

    if class != EXTERNAL {
        return Ok(Vec::new());
    }

    let of_type = PresetsOfTypeFields::new(layout)?;
    let fields = PresetFields::new(layout)?;
    let mut presets = Vec::new();

    for (hero, group) in dict_refs(process, layout.follow(process, storage, &PRESETS)?)? {
        let hero_id = (hero != GLOBAL).then_some(hero);
        let g = process.block(group, of_type.span)?;

        for (list, accessories) in [
            (g.ptr(of_type.artifacts), false),
            (g.ptr(of_type.accessories), true),
        ] {
            for addr in list_refs(process, list)?.into_iter().filter(|&a| a != 0) {
                let b = process.block(addr, fields.span)?;
                presets.push(GearPreset {
                    id: b.i64(fields.id),
                    hero_id,
                    name: string(process, b.ptr(fields.name))?,
                    accessories,
                    artifact_ids: list_i32(process, b.ptr(fields.ids))?,
                });
            }
        }
    }

    Ok(presets)
}
