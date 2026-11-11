"""20 indoor house scenarios for home / service robots.

Schema:
    name, title, tasks, description, seed
    house:   {width, depth, height, program (see layout.PROGRAMS) | rooms: [...], open_plan, min_room}
    style:   modern | scandinavian | rustic | industrial | dark
    clutter: 0..1, clutter_theme: tidy | messy | kids | laundry | moving | party
    doors_open (prob), front_door_open, curtains (prob), plants (prob), stairs (bool)
    people, people_poses, pets, pet_kinds
    lights_on, light_power, warm_light, floor_override (material role)
    environment: {lighting (agrifield presets), exposure}
    cameras: robot_head | robot_vacuum | tabletop | room_corner | topdown
"""

import copy

_BASE = dict(
    seed=0,
    house=dict(width=10.0, depth=8.0, height=2.6, program="apartment_2bed"),
    style="modern",
    clutter=0.4,
    clutter_theme="tidy",
    doors_open=0.7,
    curtains=0.5,
    plants=0.6,
    people=0,
    pets=0,
    lights_on=False,
    environment=dict(lighting="morning", exposure=1.4),
    cameras=["robot_head", "robot_vacuum", "tabletop", "topdown"],
)


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def H(name, title, tasks, description, **kw):
    sc = _merge(_BASE, dict(name=name, title=title, tasks=tasks, description=description, **kw))
    sc["seed"] = kw.get("seed", sum(map(ord, name)) * 6151 % 100003)
    return sc


NIGHT = dict(lighting="night", exposure=0.8)
EVENING = dict(lighting="dusk", exposure=-1.3)

SCENARIOS = [
    H("studio_tidy_morning", "Tidy studio apartment, morning sun", ["navigation", "mapping"],
      "One-room studio with kitchenette and bathroom; low clutter, sunlight through the windows.",
      house=dict(width=7.0, depth=5.5, program="studio"), style="scandinavian", clutter=0.2),
    H("studio_messy_evening", "Messy studio in the evening", ["navigation", "object_search", "tidying"],
      "Clothes, shoes and bags on the floor; ceiling and table lamps on after sunset.",
      house=dict(width=7.0, depth=5.5, program="studio"), style="modern", clutter=0.9, clutter_theme="messy",
      lights_on=True, environment=EVENING),
    H("apartment_vacuum_robot", "Two-bedroom apartment, vacuum robot view", ["coverage_planning", "obstacle_detection"],
      "Floor-level camera of a robot vacuum: chair legs, cables-height clutter, rugs and thresholds.",
      house=dict(width=10.0, depth=8.0, program="apartment_2bed"), clutter=0.6, clutter_theme="messy",
      cameras=["robot_vacuum", "robot_head", "topdown"]),
    H("apartment_night_lamps", "Apartment at night, lamps only", ["navigation", "low_light"],
      "Night with warm ceiling and table lamps; the robot carries a small headlight.",
      house=dict(width=10.0, depth=8.0, program="apartment_2bed"), style="rustic", lights_on=True,
      light_power=0.6, environment=NIGHT),
    H("family_house_kids_toys", "Family house with toys everywhere", ["tidying", "object_detection", "grasping"],
      "Blocks, balls, teddies and toy cars across living room and kids room floors.",
      house=dict(width=13.0, depth=10.0, program="family_3bed"), clutter=0.8, clutter_theme="kids",
      cameras=["robot_head", "robot_vacuum", "tabletop", "topdown"]),
    H("family_kitchen_manipulation", "Kitchen manipulation - counters and table", ["grasping", "tabletop", "object_detection"],
      "Busy counters and dining table: mugs, bottles, bowls, plates, fruit; tabletop camera on supports.",
      house=dict(width=12.0, depth=9.0, program="family_3bed", open_plan=True), clutter=1.0,
      cameras=["tabletop", "robot_head", "room_corner", "topdown"]),
    H("family_people_and_pets", "Family home with people and pets", ["person_detection", "social_navigation", "pet_avoidance"],
      "Residents standing and bending, a dog and a cat in the rooms the robot drives through.",
      house=dict(width=13.0, depth=10.0, program="family_3bed"), people=3, pets=2,
      people_poses=["standing", "standing", "bending", "crouching"], environment=dict(lighting="afternoon", exposure=1.4)),
    H("bungalow_rustic_afternoon", "Rustic bungalow, afternoon", ["navigation", "mapping", "domain_shift"],
      "Dark wood, warm textiles, rugs; long low sun through the windows.",
      house=dict(width=12.0, depth=8.5, program="bungalow"), style="rustic", environment=dict(lighting="afternoon", exposure=1.6)),
    H("loft_industrial_open_plan", "Industrial open-plan loft", ["navigation", "mapping", "large_spaces"],
      "Concrete floors, grey walls, open kitchen-living space with wide openings.",
      house=dict(width=14.0, depth=9.0, program="loft", open_plan=True, height=3.2), style="industrial",
      environment=dict(lighting="noon", exposure=1.7)),
    H("scandinavian_minimal_noon", "Minimal Scandinavian home", ["navigation", "low_texture"],
      "White walls, pale wood, very little clutter - low-texture scenes for visual odometry.",
      house=dict(width=10.0, depth=8.0, program="apartment_2bed"), style="scandinavian", clutter=0.1, plants=0.3,
      environment=dict(lighting="noon", exposure=1.7)),
    H("closed_doors_navigation", "Small house with most doors closed", ["door_detection", "door_opening", "navigation"],
      "Doors mostly closed or ajar (open angle annotated) - door detection and opening tasks.",
      house=dict(width=11.0, depth=8.0, program="apartment_2bed"), doors_open=0.15, front_door_open=0.0,
      cameras=["robot_head", "room_corner", "topdown"]),
    H("villa_multi_room_mapping", "Large villa, many rooms", ["mapping", "exploration", "room_classification"],
      "Eleven rooms incl. office, laundry and two bathrooms; room segmentation via per-room floor instances.",
      house=dict(width=17.0, depth=13.0, program="villa"), style="modern", clutter=0.35,
      cameras=["robot_head", "room_corner", "topdown"]),
    H("elderly_care_home", "Care home with residents", ["assistive_robotics", "person_detection", "fall_hazards"],
      "Bright, tidy rooms with residents standing or bending, stairs as a hazard, lights on.",
      house=dict(width=12.0, depth=9.0, program="care_home"), style="scandinavian", people=2,
      people_poses=["standing", "bending"], stairs=True, lights_on=True, clutter=0.25,
      environment=dict(lighting="overcast", exposure=1.0)),
    H("home_office_desks", "Home office with two workrooms", ["object_detection", "tabletop", "navigation"],
      "Desks with monitors, laptops, mugs and books; office chairs and shelving.",
      house=dict(width=12.0, depth=8.0, program="office_home"), clutter=0.6, style="modern",
      cameras=["tabletop", "robot_head", "topdown"]),
    H("moving_day_boxes", "Moving day - cardboard boxes", ["obstacle_detection", "navigation", "box_detection"],
      "Stacks of cardboard boxes in every room, doors propped open.",
      house=dict(width=11.0, depth=8.0, program="apartment_2bed"), clutter=0.7, clutter_theme="moving",
      doors_open=1.0, plants=0.1, cameras=["robot_head", "robot_vacuum", "topdown"]),
    H("party_aftermath", "After the party", ["tidying", "grasping", "object_detection"],
      "Bottles, cans and cups everywhere, some knocked over; evening lights.",
      house=dict(width=12.0, depth=9.0, program="family_3bed", open_plan=True), clutter=1.0, clutter_theme="party",
      lights_on=True, environment=EVENING, cameras=["tabletop", "robot_head", "robot_vacuum", "topdown"]),
    H("laundry_day", "Laundry day", ["deformable_objects", "grasping", "tidying"],
      "Clothes piles and laundry baskets on the floors, washing machines in the laundry room.",
      house=dict(width=12.0, depth=8.5, program="bungalow"), clutter=0.8, clutter_theme="laundry", style="scandinavian"),
    H("dark_low_contrast", "Dark interior, low contrast", ["navigation", "low_light", "domain_shift"],
      "Black furniture on dark floors under dim evening light - hard for depth and segmentation.",
      house=dict(width=10.0, depth=8.0, program="apartment_2bed"), style="dark", lights_on=True, light_power=0.5,
      environment=EVENING),
    H("glass_and_mirrors", "Glass tables, mirrors and big windows", ["transparent_objects", "depth_estimation"],
      "Glass coffee/dining tables, mirrors, glass bottles and floor-level windows (sensor failure cases).",
      house=dict(width=10.0, depth=8.0, program="apartment_1bed"), style="modern", clutter=0.6, curtains=0.0,
      environment=dict(lighting="noon", exposure=1.7), glass_p=1.0),
    H("pet_home_vacuum_night", "Pet home at night - vacuum robot", ["pet_avoidance", "obstacle_detection", "night_operation"],
      "Dogs and cats lying on the floor at night; low vacuum camera with its own light.",
      house=dict(width=10.0, depth=8.0, program="apartment_2bed"), pets=3, pet_kinds=["dog", "cat"], clutter=0.5,
      clutter_theme="messy", environment=NIGHT, lights_on=False, cameras=["robot_vacuum", "robot_head", "topdown"]),
]

BY_NAME = {s["name"]: s for s in SCENARIOS}


def get(name):
    return copy.deepcopy(BY_NAME[name])
