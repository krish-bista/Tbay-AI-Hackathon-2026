/**
 * Landing page feed data — kept separate from the UI so it can be swapped for
 * live backend data later (see getLandingFeed below).
 *
 * These are real posts from our two challenge CSVs (main_contestant.csv and
 * bonus_contestant.csv), with the category / severity our pipeline assigned.
 * Usernames and links are removed, and a few locations were corrected by hand.
 * The CSVs have no timestamps, so each card shows its source dataset instead.
 *
 * Shape: { kind: 'flood' | 'wildfire' | 'earthquake' | 'explosion' | 'storm',
 *          category?: backend category key (floods only),
 *          severity?: 'critical' | 'high' | 'medium' (floods only),
 *          location, message, source }
 */

export const LANDING_FEED = [
  { kind: 'flood', category: 'infrastructure_damage', severity: 'medium', location: 'Canmore, AB', message: 'Flooding of #TCH eastbound just west of Lac des Arcs (9 pm, June 22) #Canmore #abflood', source: 'Alberta Floods 2013' },
  { kind: 'flood', category: 'evacuation', severity: 'high', location: 'Jamestown, Colorado', message: '#Breaking: Jamestown, Colorado, is under mandatory evacuation order due to flash flooding', source: 'World Disasters' },
  { kind: 'flood', category: 'weather_water_levels', severity: 'medium', location: 'Edmonton, AB', message: 'Flood watch for N. Sask R. means levels are rising and will approach or may exceed bank. #yeg #abflood', source: 'Alberta Floods 2013' },
  { kind: 'flood', category: 'weather_water_levels', severity: 'medium', location: 'Manila, Philippines', message: 'FLOOD UPDATES as of 1:32 PM: Recto Morayta gutter deep. Rizal Recto half tire deep.', source: 'World Disasters' },
  { kind: 'wildfire', location: 'New South Wales', message: 'Sending lots of love to all those affected by the NSW fires.', source: 'World Disasters' },
  { kind: 'flood', category: 'rescue_help', severity: 'critical', location: 'Sunnyside, Calgary', message: 'Need help in Sunnyside this weekend? Get in touch here #yycflood', source: 'Alberta Floods 2013' },
  { kind: 'flood', category: 'infrastructure_damage', severity: 'high', location: 'New York, USA', message: 'Hurricane Sandy destroys Seaside Heights, floods New York and leaves millions without power', source: 'World Disasters' },
  { kind: 'flood', category: 'weather_water_levels', severity: 'medium', location: 'Bow River, Calgary', message: 'Peak flow of Bow River: 1700 m³/s. Niagara Falls: 1834 m³/s. #yycflood', source: 'Alberta Floods 2013' },
  { kind: 'flood', category: 'rescue_help', severity: 'critical', location: 'Cainta, Rizal, Philippines', message: '#rescuePH Residents of Tahanang Walang Hagdan, #8 Aida street, Marick Subd. Cainta, Rizal.', source: 'World Disasters' },
  { kind: 'flood', category: 'weather_water_levels', severity: 'medium', location: 'High River, AB', message: 'Premier Redford reacts to gutted gift shop in flooded High River. #abflood', source: 'Alberta Floods 2013' },
  { kind: 'earthquake', location: 'Costa Rica', message: 'Reports that quake has triggered landslides inland in Costa Rica', source: 'World Disasters' },
  { kind: 'flood', category: 'weather_water_levels', severity: 'high', location: 'Boulder County, Colorado', message: '3 dead in Colorado flooding after body of adult male discovered in Boulder County', source: 'World Disasters' },
  { kind: 'flood', category: 'infrastructure_damage', severity: 'medium', location: 'Bowness, Calgary', message: 'Power is on next door and most of Bowness. You could probably come home. #yycflood', source: 'Alberta Floods 2013' },
  { kind: 'flood', category: 'weather_water_levels', severity: 'medium', location: 'Pedro Gil, Manila', message: 'Knee high flood at Pedro Gil to PGH. #floodsPH #mmda', source: 'World Disasters' },
  { kind: 'flood', category: 'weather_water_levels', severity: 'medium', location: 'Medicine Hat, AB', message: 'Medicine Hat Public School Dist #76 and Catholic Board: joint statement on school closures. #mhflood', source: 'Alberta Floods 2013' },
  { kind: 'explosion', location: 'West, Texas', message: 'Large explosion at Texas fertilizer plant; multiple injuries reported', source: 'World Disasters' },
  { kind: 'flood', category: 'weather_water_levels', severity: 'medium', location: 'Brisbane, QLD', message: 'I might not be able to get to work on Tuesday, Brisbane CBD might be flooded', source: 'World Disasters' },
  { kind: 'flood', category: 'rescue_help', severity: 'critical', location: 'Sta. Rosa, Laguna, Philippines', message: '#RescuePH my kapamilyas in Garden Villa 3, Sta. Rosa, Laguna need help. #RescuePH', source: 'World Disasters' },
  { kind: 'flood', category: 'weather_water_levels', severity: 'medium', location: 'Bundaberg, QLD', message: 'An aerial view of the flood in North Bundy #bigwet #devastation', source: 'World Disasters' },
];

/** Total posts across both challenge CSVs (8,024 + 61,159); used if the API is unreachable. */
export const FALLBACK_POST_COUNT = 69183;

/**
 * Single place to swap in live data later (e.g. a backend highlights endpoint).
 * Must resolve to an array in the LANDING_FEED shape.
 */
export async function getLandingFeed() {
  return LANDING_FEED;
}
