'use strict';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

const MEAL_TYPES = [
  { id: 'breakfast', label: 'Breakfast' },
  { id: 'lunch', label: 'Lunch' },
  { id: 'dinner', label: 'Dinner' },
];

const BUDGET_TARGET = {
  tight: 35,
  balanced: 50,
  generous: 65,
};

const STORAGE_KEY = 'gumaca-family-meal-selector-v1';
const MIN_PAX = 1;
const MAX_PAX = 24;

const INGREDIENT_PRICES = {
  Rice: { unit: 'g', price: 0.058 },
  Pandesal: { unit: 'pc', price: 4.0 },
  Egg: { unit: 'pc', price: 8.0 },
  Tomato: { unit: 'g', price: 0.11 },
  'Dried Fish': { unit: 'g', price: 0.37 },
  'Cocoa Powder': { unit: 'g', price: 0.62 },
  Sugar: { unit: 'g', price: 0.06 },
  'Evaporated Milk': { unit: 'ml', price: 0.09 },
  Tofu: { unit: 'g', price: 0.13 },
  Ginger: { unit: 'g', price: 0.2 },
  Garlic: { unit: 'g', price: 0.18 },
  'Spring Onion': { unit: 'g', price: 0.22 },
  Chicken: { unit: 'g', price: 0.22 },
  Calamansi: { unit: 'pc', price: 3.0 },
  Carrot: { unit: 'g', price: 0.1 },
  Cabbage: { unit: 'g', price: 0.06 },
  Potato: { unit: 'g', price: 0.085 },
  Onion: { unit: 'g', price: 0.12 },
  'Sardines Can': { unit: 'can', price: 32.0 },
  Eggplant: { unit: 'g', price: 0.09 },
  Oats: { unit: 'g', price: 0.19 },
  Banana: { unit: 'pc', price: 8.0 },
  'Mung Beans': { unit: 'g', price: 0.09 },
  Malunggay: { unit: 'g', price: 0.08 },
  Tinapa: { unit: 'g', price: 0.34 },
  Tilapia: { unit: 'g', price: 0.24 },
  Squash: { unit: 'g', price: 0.08 },
  'String Beans': { unit: 'g', price: 0.09 },
  Pork: { unit: 'g', price: 0.29 },
  'Bell Pepper': { unit: 'g', price: 0.24 },
  Raisins: { unit: 'g', price: 0.44 },
  Shrimp: { unit: 'g', price: 0.48 },
  'Coconut Milk': { unit: 'ml', price: 0.11 },
  'Taro Leaves': { unit: 'g', price: 0.09 },
  Galunggong: { unit: 'g', price: 0.24 },
  Beef: { unit: 'g', price: 0.44 },
  'Soy Sauce': { unit: 'ml', price: 0.08 },
  Vinegar: { unit: 'ml', price: 0.05 },
  'Pancit Bihon': { unit: 'g', price: 0.17 },
  'Baguio Beans': { unit: 'g', price: 0.11 },
  'Tamarind Mix': { unit: 'g', price: 0.54 },
  Kangkong: { unit: 'g', price: 0.07 },
  Radish: { unit: 'g', price: 0.07 },
  Pechay: { unit: 'g', price: 0.09 },
  'Curry Powder': { unit: 'g', price: 0.73 },
  Ampalaya: { unit: 'g', price: 0.1 },
  'Pancit Canton': { unit: 'g', price: 0.18 },
  'Green Papaya': { unit: 'g', price: 0.07 },
  'Fish Sauce': { unit: 'ml', price: 0.08 },
  Chayote: { unit: 'g', price: 0.07 },
  Lemon: { unit: 'pc', price: 12.0 },
  Chili: { unit: 'g', price: 0.35 },
  'Cooking Oil': { unit: 'ml', price: 0.07 },
  'Tomato Sauce': { unit: 'ml', price: 0.1 },
  'Young Jackfruit': { unit: 'g', price: 0.09 },
  Bangus: { unit: 'g', price: 0.3 },
};

const GROCERY_CATEGORIES = [
  { id: 'produce', label: 'Produce & Vegetables' },
  { id: 'meat', label: 'Meat & Poultry' },
  { id: 'seafood', label: 'Seafood' },
  { id: 'dairy-eggs', label: 'Dairy, Eggs & Chilled' },
  { id: 'bakery', label: 'Bakery' },
  { id: 'pantry', label: 'Pantry & Dry Goods' },
  { id: 'other', label: 'Other Essentials' },
];

const INGREDIENT_CATEGORY = {
  Rice: 'pantry',
  Pandesal: 'bakery',
  Egg: 'dairy-eggs',
  Tomato: 'produce',
  'Dried Fish': 'seafood',
  'Cocoa Powder': 'pantry',
  Sugar: 'pantry',
  'Evaporated Milk': 'dairy-eggs',
  Tofu: 'dairy-eggs',
  Ginger: 'produce',
  Garlic: 'produce',
  'Spring Onion': 'produce',
  Chicken: 'meat',
  Calamansi: 'produce',
  Carrot: 'produce',
  Cabbage: 'produce',
  Potato: 'produce',
  Onion: 'produce',
  'Sardines Can': 'seafood',
  Eggplant: 'produce',
  Oats: 'pantry',
  Banana: 'produce',
  'Mung Beans': 'pantry',
  Malunggay: 'produce',
  Tinapa: 'seafood',
  Tilapia: 'seafood',
  Squash: 'produce',
  'String Beans': 'produce',
  Pork: 'meat',
  'Bell Pepper': 'produce',
  Raisins: 'pantry',
  Shrimp: 'seafood',
  'Coconut Milk': 'pantry',
  'Taro Leaves': 'produce',
  Galunggong: 'seafood',
  Beef: 'meat',
  'Soy Sauce': 'pantry',
  Vinegar: 'pantry',
  'Pancit Bihon': 'pantry',
  'Baguio Beans': 'produce',
  'Tamarind Mix': 'pantry',
  Kangkong: 'produce',
  Radish: 'produce',
  Pechay: 'produce',
  'Curry Powder': 'pantry',
  Ampalaya: 'produce',
  'Pancit Canton': 'pantry',
  'Green Papaya': 'produce',
  'Fish Sauce': 'pantry',
  Chayote: 'produce',
  Lemon: 'produce',
  Chili: 'produce',
  'Cooking Oil': 'pantry',
  'Tomato Sauce': 'pantry',
  'Young Jackfruit': 'produce',
  Bangus: 'seafood',
};

const KIDS_MEAL_IDS = new Set([
  'pandesal-itlog-kamatis',
  'champorado-tuyo',
  'lugaw-tokwa',
  'arroz-caldo-manok',
  'tortang-talong-sinangag',
  'sopas-manok',
  'taho-saging',
  'suman-itlog-saging',
  'adobong-manok',
  'tinolang-manok',
  'pork-menudo',
  'chicken-afritada',
  'pancit-bihon-tokwa',
  'sinigang-bangus',
  'chicken-curry',
  'tokwa-gulay-stirfry',
  'pork-adobo',
  'nilagang-baka',
  'pancit-canton-gulay',
  'chicken-adobo-sa-gata',
  'chopsuey-tokwa',
]);

const MEALS = [
  {
    id: 'pandesal-itlog-kamatis',
    name: 'Pandesal, Itlog at Kamatis',
    mealType: 'breakfast',
    costPerPerson: 32,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Pandesal', qty: 2, unit: 'pc' },
      { name: 'Egg', qty: 1, unit: 'pc' },
      { name: 'Tomato', qty: 60, unit: 'g' },
    ],
  },
  {
    id: 'champorado-tuyo',
    name: 'Champorado with Tuyo',
    mealType: 'breakfast',
    costPerPerson: 42,
    tags: ['seafood'],
    ingredients: [
      { name: 'Rice', qty: 65, unit: 'g' },
      { name: 'Cocoa Powder', qty: 10, unit: 'g' },
      { name: 'Sugar', qty: 12, unit: 'g' },
      { name: 'Evaporated Milk', qty: 40, unit: 'ml' },
      { name: 'Dried Fish', qty: 25, unit: 'g' },
    ],
  },
  {
    id: 'lugaw-tokwa',
    name: 'Lugaw with Tokwa',
    mealType: 'breakfast',
    costPerPerson: 34,
    tags: ['vegetarian', 'budget'],
    ingredients: [
      { name: 'Rice', qty: 70, unit: 'g' },
      { name: 'Tofu', qty: 70, unit: 'g' },
      { name: 'Ginger', qty: 7, unit: 'g' },
      { name: 'Garlic', qty: 5, unit: 'g' },
      { name: 'Spring Onion', qty: 8, unit: 'g' },
    ],
  },
  {
    id: 'arroz-caldo-manok',
    name: 'Arroz Caldo Manok',
    mealType: 'breakfast',
    costPerPerson: 52,
    tags: ['comfort'],
    ingredients: [
      { name: 'Rice', qty: 70, unit: 'g' },
      { name: 'Chicken', qty: 90, unit: 'g' },
      { name: 'Ginger', qty: 8, unit: 'g' },
      { name: 'Garlic', qty: 5, unit: 'g' },
      { name: 'Spring Onion', qty: 8, unit: 'g' },
      { name: 'Fish Sauce', qty: 6, unit: 'ml' },
    ],
  },
  {
    id: 'tortang-talong-sinangag',
    name: 'Tortang Talong with Sinangag',
    mealType: 'breakfast',
    costPerPerson: 38,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Eggplant', qty: 130, unit: 'g' },
      { name: 'Egg', qty: 1, unit: 'pc' },
      { name: 'Rice', qty: 75, unit: 'g' },
      { name: 'Garlic', qty: 4, unit: 'g' },
      { name: 'Onion', qty: 20, unit: 'g' },
    ],
  },
  {
    id: 'ginisang-sardinas-pandesal',
    name: 'Ginisang Sardinas with Pandesal',
    mealType: 'breakfast',
    costPerPerson: 39,
    tags: ['seafood'],
    ingredients: [
      { name: 'Sardines Can', qty: 0.16, unit: 'can' },
      { name: 'Pandesal', qty: 2, unit: 'pc' },
      { name: 'Onion', qty: 20, unit: 'g' },
      { name: 'Tomato', qty: 40, unit: 'g' },
      { name: 'Garlic', qty: 4, unit: 'g' },
    ],
  },
  {
    id: 'sopas-manok',
    name: 'Sopas na Manok',
    mealType: 'breakfast',
    costPerPerson: 48,
    tags: ['comfort'],
    ingredients: [
      { name: 'Chicken', qty: 70, unit: 'g' },
      { name: 'Cabbage', qty: 70, unit: 'g' },
      { name: 'Carrot', qty: 40, unit: 'g' },
      { name: 'Potato', qty: 70, unit: 'g' },
      { name: 'Evaporated Milk', qty: 30, unit: 'ml' },
    ],
  },
  {
    id: 'taho-saging',
    name: 'Taho at Saging',
    mealType: 'breakfast',
    costPerPerson: 31,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Tofu', qty: 120, unit: 'g' },
      { name: 'Banana', qty: 1, unit: 'pc' },
      { name: 'Sugar', qty: 8, unit: 'g' },
    ],
  },
  {
    id: 'suman-itlog-saging',
    name: 'Suman, Itlog at Saging',
    mealType: 'breakfast',
    costPerPerson: 36,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Rice', qty: 80, unit: 'g' },
      { name: 'Egg', qty: 1, unit: 'pc' },
      { name: 'Banana', qty: 1, unit: 'pc' },
      { name: 'Sugar', qty: 6, unit: 'g' },
    ],
  },
  {
    id: 'monggo-itlog-breakfast',
    name: 'Ginisang Monggo at Itlog',
    mealType: 'breakfast',
    costPerPerson: 40,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Mung Beans', qty: 60, unit: 'g' },
      { name: 'Egg', qty: 1, unit: 'pc' },
      { name: 'Tomato', qty: 40, unit: 'g' },
      { name: 'Onion', qty: 25, unit: 'g' },
      { name: 'Garlic', qty: 4, unit: 'g' },
    ],
  },
  {
    id: 'adobong-manok',
    name: 'Adobong Manok',
    mealType: 'lunch',
    costPerPerson: 72,
    tags: ['classic'],
    ingredients: [
      { name: 'Chicken', qty: 150, unit: 'g' },
      { name: 'Soy Sauce', qty: 15, unit: 'ml' },
      { name: 'Vinegar', qty: 15, unit: 'ml' },
      { name: 'Garlic', qty: 6, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'tinolang-manok',
    name: 'Tinolang Manok',
    mealType: 'lunch',
    costPerPerson: 70,
    tags: ['soup'],
    ingredients: [
      { name: 'Chicken', qty: 150, unit: 'g' },
      { name: 'Green Papaya', qty: 120, unit: 'g' },
      { name: 'Malunggay', qty: 40, unit: 'g' },
      { name: 'Ginger', qty: 8, unit: 'g' },
      { name: 'Garlic', qty: 4, unit: 'g' },
      { name: 'Fish Sauce', qty: 8, unit: 'ml' },
      { name: 'Rice', qty: 85, unit: 'g' },
    ],
  },
  {
    id: 'monggo-tinapa',
    name: 'Ginisang Monggo with Tinapa',
    mealType: 'lunch',
    costPerPerson: 64,
    tags: ['seafood'],
    ingredients: [
      { name: 'Mung Beans', qty: 70, unit: 'g' },
      { name: 'Tinapa', qty: 40, unit: 'g' },
      { name: 'Malunggay', qty: 30, unit: 'g' },
      { name: 'Tomato', qty: 45, unit: 'g' },
      { name: 'Onion', qty: 25, unit: 'g' },
      { name: 'Rice', qty: 85, unit: 'g' },
    ],
  },
  {
    id: 'pinakbet-tilapia',
    name: 'Pinakbet with Inihaw na Tilapia',
    mealType: 'lunch',
    costPerPerson: 78,
    tags: ['seafood'],
    ingredients: [
      { name: 'Tilapia', qty: 150, unit: 'g' },
      { name: 'Squash', qty: 100, unit: 'g' },
      { name: 'String Beans', qty: 80, unit: 'g' },
      { name: 'Eggplant', qty: 90, unit: 'g' },
      { name: 'Tomato', qty: 40, unit: 'g' },
      { name: 'Onion', qty: 30, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'pork-menudo',
    name: 'Pork Menudo',
    mealType: 'lunch',
    costPerPerson: 80,
    tags: ['pork'],
    ingredients: [
      { name: 'Pork', qty: 150, unit: 'g' },
      { name: 'Potato', qty: 90, unit: 'g' },
      { name: 'Carrot', qty: 60, unit: 'g' },
      { name: 'Tomato Sauce', qty: 45, unit: 'ml' },
      { name: 'Bell Pepper', qty: 35, unit: 'g' },
      { name: 'Raisins', qty: 8, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'ginataang-kalabasa-hipon',
    name: 'Ginataang Kalabasa at Hipon',
    mealType: 'lunch',
    costPerPerson: 82,
    tags: ['seafood'],
    ingredients: [
      { name: 'Shrimp', qty: 120, unit: 'g' },
      { name: 'Squash', qty: 120, unit: 'g' },
      { name: 'String Beans', qty: 90, unit: 'g' },
      { name: 'Coconut Milk', qty: 90, unit: 'ml' },
      { name: 'Ginger', qty: 6, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'chicken-afritada',
    name: 'Chicken Afritada',
    mealType: 'lunch',
    costPerPerson: 76,
    tags: ['family-favorite'],
    ingredients: [
      { name: 'Chicken', qty: 150, unit: 'g' },
      { name: 'Potato', qty: 90, unit: 'g' },
      { name: 'Carrot', qty: 70, unit: 'g' },
      { name: 'Bell Pepper', qty: 35, unit: 'g' },
      { name: 'Tomato Sauce', qty: 50, unit: 'ml' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'laing-galunggong',
    name: 'Laing with Galunggong',
    mealType: 'lunch',
    costPerPerson: 74,
    tags: ['seafood'],
    ingredients: [
      { name: 'Taro Leaves', qty: 80, unit: 'g' },
      { name: 'Coconut Milk', qty: 100, unit: 'ml' },
      { name: 'Galunggong', qty: 90, unit: 'g' },
      { name: 'Chili', qty: 4, unit: 'g' },
      { name: 'Garlic', qty: 5, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'bistek-tagalog',
    name: 'Bistek Tagalog',
    mealType: 'lunch',
    costPerPerson: 88,
    tags: ['beef'],
    ingredients: [
      { name: 'Beef', qty: 140, unit: 'g' },
      { name: 'Onion', qty: 45, unit: 'g' },
      { name: 'Calamansi', qty: 2, unit: 'pc' },
      { name: 'Soy Sauce', qty: 18, unit: 'ml' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'pancit-bihon-tokwa',
    name: 'Pancit Bihon with Tokwa',
    mealType: 'lunch',
    costPerPerson: 66,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Pancit Bihon', qty: 85, unit: 'g' },
      { name: 'Tofu', qty: 80, unit: 'g' },
      { name: 'Cabbage', qty: 80, unit: 'g' },
      { name: 'Carrot', qty: 45, unit: 'g' },
      { name: 'Baguio Beans', qty: 70, unit: 'g' },
      { name: 'Garlic', qty: 5, unit: 'g' },
    ],
  },
  {
    id: 'ampalaya-itlog-lunch',
    name: 'Ginisang Ampalaya with Itlog',
    mealType: 'lunch',
    costPerPerson: 62,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Ampalaya', qty: 110, unit: 'g' },
      { name: 'Egg', qty: 1, unit: 'pc' },
      { name: 'Tomato', qty: 40, unit: 'g' },
      { name: 'Onion', qty: 25, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'ginataang-langka',
    name: 'Ginataang Langka',
    mealType: 'lunch',
    costPerPerson: 68,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Young Jackfruit', qty: 130, unit: 'g' },
      { name: 'Coconut Milk', qty: 100, unit: 'ml' },
      { name: 'String Beans', qty: 70, unit: 'g' },
      { name: 'Garlic', qty: 5, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'sinigang-bangus',
    name: 'Sinigang na Bangus',
    mealType: 'dinner',
    costPerPerson: 84,
    tags: ['seafood'],
    ingredients: [
      { name: 'Bangus', qty: 150, unit: 'g' },
      { name: 'Tamarind Mix', qty: 12, unit: 'g' },
      { name: 'Radish', qty: 70, unit: 'g' },
      { name: 'Kangkong', qty: 60, unit: 'g' },
      { name: 'Tomato', qty: 40, unit: 'g' },
      { name: 'Onion', qty: 30, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'paksiw-galunggong',
    name: 'Paksiw na Galunggong',
    mealType: 'dinner',
    costPerPerson: 74,
    tags: ['seafood'],
    ingredients: [
      { name: 'Galunggong', qty: 160, unit: 'g' },
      { name: 'Vinegar', qty: 20, unit: 'ml' },
      { name: 'Garlic', qty: 6, unit: 'g' },
      { name: 'Ginger', qty: 8, unit: 'g' },
      { name: 'Eggplant', qty: 80, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'chicken-curry',
    name: 'Chicken Curry',
    mealType: 'dinner',
    costPerPerson: 82,
    tags: ['family-favorite'],
    ingredients: [
      { name: 'Chicken', qty: 150, unit: 'g' },
      { name: 'Potato', qty: 90, unit: 'g' },
      { name: 'Carrot', qty: 60, unit: 'g' },
      { name: 'Coconut Milk', qty: 90, unit: 'ml' },
      { name: 'Curry Powder', qty: 4, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'tokwa-gulay-stirfry',
    name: 'Tokwa at Gulay Stir Fry',
    mealType: 'dinner',
    costPerPerson: 64,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Tofu', qty: 120, unit: 'g' },
      { name: 'Cabbage', qty: 90, unit: 'g' },
      { name: 'Carrot', qty: 45, unit: 'g' },
      { name: 'Baguio Beans', qty: 80, unit: 'g' },
      { name: 'Soy Sauce', qty: 12, unit: 'ml' },
      { name: 'Garlic', qty: 5, unit: 'g' },
      { name: 'Rice', qty: 85, unit: 'g' },
    ],
  },
  {
    id: 'pork-adobo',
    name: 'Pork Adobo',
    mealType: 'dinner',
    costPerPerson: 79,
    tags: ['pork'],
    ingredients: [
      { name: 'Pork', qty: 150, unit: 'g' },
      { name: 'Soy Sauce', qty: 16, unit: 'ml' },
      { name: 'Vinegar', qty: 16, unit: 'ml' },
      { name: 'Garlic', qty: 6, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'nilagang-baka',
    name: 'Nilagang Baka',
    mealType: 'dinner',
    costPerPerson: 95,
    tags: ['beef'],
    ingredients: [
      { name: 'Beef', qty: 150, unit: 'g' },
      { name: 'Potato', qty: 90, unit: 'g' },
      { name: 'Pechay', qty: 80, unit: 'g' },
      { name: 'Cabbage', qty: 70, unit: 'g' },
      { name: 'Onion', qty: 25, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'ampalaya-itlog-dinner',
    name: 'Ampalaya at Itlog',
    mealType: 'dinner',
    costPerPerson: 60,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Ampalaya', qty: 120, unit: 'g' },
      { name: 'Egg', qty: 1, unit: 'pc' },
      { name: 'Tomato', qty: 40, unit: 'g' },
      { name: 'Onion', qty: 20, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'pancit-canton-gulay',
    name: 'Pancit Canton with Gulay',
    mealType: 'dinner',
    costPerPerson: 65,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Pancit Canton', qty: 95, unit: 'g' },
      { name: 'Cabbage', qty: 80, unit: 'g' },
      { name: 'Carrot', qty: 45, unit: 'g' },
      { name: 'Baguio Beans', qty: 80, unit: 'g' },
      { name: 'Soy Sauce', qty: 12, unit: 'ml' },
      { name: 'Garlic', qty: 5, unit: 'g' },
    ],
  },
  {
    id: 'ginataang-tilapia',
    name: 'Ginataang Tilapia',
    mealType: 'dinner',
    costPerPerson: 80,
    tags: ['seafood'],
    ingredients: [
      { name: 'Tilapia', qty: 150, unit: 'g' },
      { name: 'Coconut Milk', qty: 95, unit: 'ml' },
      { name: 'Ginger', qty: 8, unit: 'g' },
      { name: 'Garlic', qty: 5, unit: 'g' },
      { name: 'String Beans', qty: 70, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'chicken-adobo-sa-gata',
    name: 'Chicken Adobo sa Gata',
    mealType: 'dinner',
    costPerPerson: 78,
    tags: ['classic'],
    ingredients: [
      { name: 'Chicken', qty: 150, unit: 'g' },
      { name: 'Coconut Milk', qty: 80, unit: 'ml' },
      { name: 'Soy Sauce', qty: 12, unit: 'ml' },
      { name: 'Vinegar', qty: 12, unit: 'ml' },
      { name: 'Garlic', qty: 6, unit: 'g' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
  {
    id: 'chopsuey-tokwa',
    name: 'Chopsuey with Tokwa',
    mealType: 'dinner',
    costPerPerson: 67,
    tags: ['vegetarian'],
    ingredients: [
      { name: 'Tofu', qty: 100, unit: 'g' },
      { name: 'Cabbage', qty: 90, unit: 'g' },
      { name: 'Carrot', qty: 50, unit: 'g' },
      { name: 'Baguio Beans', qty: 80, unit: 'g' },
      { name: 'Bell Pepper', qty: 35, unit: 'g' },
      { name: 'Garlic', qty: 5, unit: 'g' },
      { name: 'Rice', qty: 85, unit: 'g' },
    ],
  },
  {
    id: 'lemon-beef-stirfry',
    name: 'Lemon Beef Stir Fry',
    mealType: 'dinner',
    costPerPerson: 90,
    tags: ['beef'],
    ingredients: [
      { name: 'Beef', qty: 130, unit: 'g' },
      { name: 'Lemon', qty: 1, unit: 'pc' },
      { name: 'Bell Pepper', qty: 35, unit: 'g' },
      { name: 'Onion', qty: 30, unit: 'g' },
      { name: 'Soy Sauce', qty: 14, unit: 'ml' },
      { name: 'Rice', qty: 90, unit: 'g' },
    ],
  },
];

const mealById = new Map(MEALS.map((meal) => [meal.id, meal]));

const state = {
  settings: {
    familySize: 6,
    budgetMode: 'balanced',
    avoidPork: false,
    avoidSeafood: false,
    preferVegetables: false,
    kidsOnly: false,
  },
  slots: {},
};

const mealDialogState = {
  day: null,
  mealTypeId: null,
  mealId: null,
  triggerButton: null,
};

const ui = {
  familySize: document.getElementById('familySize'),
  budgetMode: document.getElementById('budgetMode'),
  avoidPork: document.getElementById('avoidPork'),
  avoidSeafood: document.getElementById('avoidSeafood'),
  preferVegetables: document.getElementById('preferVegetables'),
  kidsOnly: document.getElementById('kidsOnly'),
  generateButton: document.getElementById('generateButton'),
  resetButton: document.getElementById('resetButton'),
  exportCsvButton: document.getElementById('exportCsvButton'),
  planner: document.getElementById('planner'),
  statMeals: document.getElementById('statMeals'),
  statWeeklyCost: document.getElementById('statWeeklyCost'),
  statDailyCost: document.getElementById('statDailyCost'),
  summaryTableBody: document.querySelector('#summaryTable tbody'),
  groceryTableBody: document.querySelector('#groceryTable tbody'),
  groceryTotal: document.getElementById('groceryTotal'),
  mealDialog: document.getElementById('mealDialog'),
  mealDialogBackdrop: document.getElementById('mealDialogBackdrop'),
  mealDialogSlot: document.getElementById('mealDialogSlot'),
  mealDialogTitle: document.getElementById('mealDialogTitle'),
  mealDialogMeta: document.getElementById('mealDialogMeta'),
  mealDialogIngredients: document.getElementById('mealDialogIngredients'),
  mealDialogClose: document.getElementById('mealDialogClose'),
  mealDialogAdd: document.getElementById('mealDialogAdd'),
};

function slotKey(day, mealType) {
  return `${day}::${mealType}`;
}

function loadState() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return;
  }

  try {
    const parsed = JSON.parse(raw);

    if (parsed.settings && typeof parsed.settings === 'object') {
      const loadedFamily = Number(parsed.settings.familySize);
      state.settings.familySize = Number.isFinite(loadedFamily)
        ? clamp(Math.round(loadedFamily), MIN_PAX, MAX_PAX)
        : state.settings.familySize;

      if (['tight', 'balanced', 'generous'].includes(parsed.settings.budgetMode)) {
        state.settings.budgetMode = parsed.settings.budgetMode;
      }

      state.settings.avoidPork = Boolean(parsed.settings.avoidPork);
      state.settings.avoidSeafood = Boolean(parsed.settings.avoidSeafood);
      state.settings.preferVegetables = Boolean(parsed.settings.preferVegetables);
      state.settings.kidsOnly = Boolean(parsed.settings.kidsOnly);
    }

    if (parsed.slots && typeof parsed.slots === 'object') {
      state.slots = parsed.slots;
    }
  } catch (_error) {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function populateFamilySizeOptions() {
  if (!ui.familySize) {
    return;
  }

  if (ui.familySize.tagName !== 'SELECT') {
    ui.familySize.min = String(MIN_PAX);
    ui.familySize.max = String(MAX_PAX);
    return;
  }

  ui.familySize.innerHTML = '';
  for (let pax = MIN_PAX; pax <= MAX_PAX; pax += 1) {
    const option = document.createElement('option');
    option.value = String(pax);
    option.textContent = `${pax}`;
    ui.familySize.appendChild(option);
  }
}

function applyStateToInputs() {
  ui.familySize.value = String(state.settings.familySize);
  ui.budgetMode.value = state.settings.budgetMode;
  ui.avoidPork.checked = state.settings.avoidPork;
  ui.avoidSeafood.checked = state.settings.avoidSeafood;
  ui.preferVegetables.checked = state.settings.preferVegetables;
  if (ui.kidsOnly) {
    ui.kidsOnly.checked = state.settings.kidsOnly;
  }
}

function readSettingsFromInputs() {
  state.settings.familySize = clamp(Math.round(Number(ui.familySize.value || 6)), MIN_PAX, MAX_PAX);
  state.settings.budgetMode = ui.budgetMode.value;
  state.settings.avoidPork = ui.avoidPork.checked;
  state.settings.avoidSeafood = ui.avoidSeafood.checked;
  state.settings.preferVegetables = ui.preferVegetables.checked;
  state.settings.kidsOnly = ui.kidsOnly ? ui.kidsOnly.checked : false;
  ui.familySize.value = String(state.settings.familySize);
}

function hasCompleteSlots() {
  for (const day of DAYS) {
    for (const mealType of MEAL_TYPES) {
      const key = slotKey(day, mealType.id);
      const slot = state.slots[key];
      if (!slot || !Array.isArray(slot.suggestionIds) || !slot.suggestionIds.length) {
        return false;
      }
      if (!slot.selectedMealId || !mealById.has(slot.selectedMealId)) {
        return false;
      }
    }
  }
  return true;
}

function sanitizeSlots() {
  for (const day of DAYS) {
    for (const mealType of MEAL_TYPES) {
      const key = slotKey(day, mealType.id);
      const slot = state.slots[key];
      if (!slot || !Array.isArray(slot.suggestionIds)) {
        return false;
      }
      slot.suggestionIds = slot.suggestionIds.filter((id) => mealById.has(id));
      if (!slot.suggestionIds.length) {
        return false;
      }
      if (!slot.selectedMealId || !mealById.has(slot.selectedMealId)) {
        slot.selectedMealId = slot.suggestionIds[0];
      }
      if (!slot.suggestionIds.includes(slot.selectedMealId)) {
        slot.suggestionIds.unshift(slot.selectedMealId);
      }
      slot.suggestionIds = slot.suggestionIds.slice(0, 3);
    }
  }
  return true;
}

function filteredMealsByType(mealType) {
  const filtered = MEALS.filter((meal) => {
    if (meal.mealType !== mealType) {
      return false;
    }
    if (state.settings.avoidPork && meal.tags.includes('pork')) {
      return false;
    }
    if (state.settings.avoidSeafood && meal.tags.includes('seafood')) {
      return false;
    }
    if (state.settings.kidsOnly && !isKidsMeal(meal)) {
      return false;
    }
    return true;
  });

  return filtered.length ? filtered : MEALS.filter((meal) => meal.mealType === mealType);
}

function isKidsMeal(meal) {
  return KIDS_MEAL_IDS.has(meal.id) || meal.tags.includes('kids');
}

function ingredientCost(ingredient) {
  const priceRef = INGREDIENT_PRICES[ingredient.name];
  if (!priceRef || priceRef.unit !== ingredient.unit) {
    return null;
  }
  return ingredient.qty * priceRef.price;
}

function mealCostPerPerson(meal) {
  let total = 0;
  let hasUnpricedIngredient = false;

  for (const ingredient of meal.ingredients) {
    const cost = ingredientCost(ingredient);
    if (cost === null) {
      hasUnpricedIngredient = true;
      continue;
    }
    total += cost;
  }

  if (!hasUnpricedIngredient) {
    return total;
  }

  return Number(meal.costPerPerson) || total;
}

function mealCostForFamily(meal) {
  return mealCostPerPerson(meal) * state.settings.familySize;
}

function scoreMeal(meal, useCounts) {
  const target = BUDGET_TARGET[state.settings.budgetMode];
  let score = Math.abs(mealCostPerPerson(meal) - target);
  score += (useCounts[meal.id] || 0) * 18;

  if (state.settings.preferVegetables && !meal.tags.includes('vegetarian')) {
    score += 14;
  }

  score += Math.random() * 11;
  return score;
}

function pickSuggestions(mealType, useCounts, excludedIds = []) {
  const excluded = new Set(excludedIds);
  const candidates = filteredMealsByType(mealType)
    .filter((meal) => !excluded.has(meal.id))
    .map((meal) => ({
      meal,
      score: scoreMeal(meal, useCounts),
    }))
    .sort((a, b) => a.score - b.score)
    .map((entry) => entry.meal);

  if (!candidates.length) {
    return filteredMealsByType(mealType)
      .map((meal) => ({ meal, score: scoreMeal(meal, useCounts) }))
      .sort((a, b) => a.score - b.score)
      .map((entry) => entry.meal)
      .slice(0, 3);
  }

  return candidates.slice(0, 3);
}

function selectedUseCounts(skipKey = null) {
  const counts = {};
  for (const day of DAYS) {
    for (const mealType of MEAL_TYPES) {
      const key = slotKey(day, mealType.id);
      if (key === skipKey) {
        continue;
      }
      const selectedId = state.slots[key]?.selectedMealId;
      if (selectedId) {
        counts[selectedId] = (counts[selectedId] || 0) + 1;
      }
    }
  }
  return counts;
}

function regenerateWeek() {
  const useCounts = {};

  for (const day of DAYS) {
    for (const mealType of MEAL_TYPES) {
      const key = slotKey(day, mealType.id);
      const suggestions = pickSuggestions(mealType.id, useCounts);
      const selectedMealId = suggestions[0]?.id || null;

      state.slots[key] = {
        suggestionIds: suggestions.map((meal) => meal.id),
        selectedMealId,
      };

      if (selectedMealId) {
        useCounts[selectedMealId] = (useCounts[selectedMealId] || 0) + 1;
      }
    }
  }

  saveState();
}

function regenerateSingleSlot(day, mealTypeId) {
  const key = slotKey(day, mealTypeId);
  const currentSlot = state.slots[key];
  const excluded = currentSlot?.suggestionIds || [];
  const useCounts = selectedUseCounts(key);
  const suggestions = pickSuggestions(mealTypeId, useCounts, excluded);

  state.slots[key] = {
    suggestionIds: suggestions.map((meal) => meal.id),
    selectedMealId: suggestions[0]?.id || null,
  };

  saveState();
}

function selectedMealFor(day, mealTypeId) {
  const key = slotKey(day, mealTypeId);
  const selectedId = state.slots[key]?.selectedMealId;
  return selectedId ? mealById.get(selectedId) || null : null;
}

function mealTypeLabel(mealTypeId) {
  return MEAL_TYPES.find((entry) => entry.id === mealTypeId)?.label || mealTypeId;
}

function mealTagLabel(meal) {
  if (isKidsMeal(meal)) {
    return 'kid-friendly';
  }
  if (meal.tags.includes('vegetarian')) {
    return 'vegetable-forward';
  }
  if (meal.tags.includes('seafood')) {
    return 'seafood';
  }
  if (meal.tags.includes('pork')) {
    return 'contains pork';
  }
  return 'family meal';
}

function mealIngredientsForFamily(meal) {
  return meal.ingredients.map((ingredient) => {
    const familyQty = ingredient.qty * state.settings.familySize;
    return `${ingredient.name}: ${formatQuantity(familyQty, ingredient.unit)}`;
  });
}

function mealDialogAvailable() {
  return Boolean(
    ui.mealDialog &&
    ui.mealDialogSlot &&
    ui.mealDialogTitle &&
    ui.mealDialogMeta &&
    ui.mealDialogIngredients &&
    ui.mealDialogAdd &&
    ui.mealDialogClose,
  );
}

function showMealFallbackPrompt(day, mealTypeId, meal, slot) {
  const ingredientLines = mealIngredientsForFamily(meal).join('\n');
  const details = [
    `${day} | ${mealTypeLabel(mealTypeId)}`,
    meal.name,
    `${formatCurrency(mealCostForFamily(meal))} per family`,
    '',
    'Ingredients:',
    ingredientLines,
  ].join('\n');

  if (slot.selectedMealId === meal.id) {
    window.alert(`${details}\n\nAlready in weekly menu.`);
    return;
  }

  if (window.confirm(`${details}\n\nAdd to weekly menu?`)) {
    state.slots[slotKey(day, mealTypeId)].selectedMealId = meal.id;
    saveState();
    renderPlanner();
    renderSummaryAndGroceries();
  }
}

function clearMealDialogState() {
  mealDialogState.day = null;
  mealDialogState.mealTypeId = null;
  mealDialogState.mealId = null;
  mealDialogState.triggerButton = null;
}

function closeMealDialog(restoreFocus = true) {
  if (!ui.mealDialog || ui.mealDialog.hidden) {
    return;
  }

  const trigger = mealDialogState.triggerButton;
  ui.mealDialog.hidden = true;
  document.body.classList.remove('dialog-open');
  clearMealDialogState();

  if (restoreFocus && trigger && document.contains(trigger)) {
    trigger.focus();
  }
}

function openMealDialog(day, mealTypeId, mealId, triggerButton = null) {
  const meal = mealById.get(mealId);
  const slot = state.slots[slotKey(day, mealTypeId)];
  if (!meal || !slot) {
    return;
  }

  if (!mealDialogAvailable()) {
    showMealFallbackPrompt(day, mealTypeId, meal, slot);
    return;
  }

  mealDialogState.day = day;
  mealDialogState.mealTypeId = mealTypeId;
  mealDialogState.mealId = mealId;
  mealDialogState.triggerButton = triggerButton;

  ui.mealDialogSlot.textContent = `${day} | ${mealTypeLabel(mealTypeId)}`;
  ui.mealDialogTitle.textContent = meal.name;
  ui.mealDialogMeta.textContent = `${formatCurrency(mealCostForFamily(meal))} per family | ${mealTagLabel(meal)}`;

  ui.mealDialogIngredients.innerHTML = '';
  for (const line of mealIngredientsForFamily(meal)) {
    const item = document.createElement('li');
    item.textContent = line;
    ui.mealDialogIngredients.appendChild(item);
  }

  const alreadySelected = slot.selectedMealId === meal.id;
  ui.mealDialogAdd.disabled = alreadySelected;
  ui.mealDialogAdd.textContent = alreadySelected ? 'Already in weekly menu' : 'Add to weekly menu';

  ui.mealDialog.hidden = false;
  document.body.classList.add('dialog-open');

  if (alreadySelected) {
    ui.mealDialogClose.focus();
  } else {
    ui.mealDialogAdd.focus();
  }
}

function addDialogMealToWeeklyMenu() {
  const { day, mealTypeId, mealId } = mealDialogState;
  if (!day || !mealTypeId || !mealId) {
    return;
  }

  const key = slotKey(day, mealTypeId);
  if (!state.slots[key] || !mealById.has(mealId)) {
    closeMealDialog(false);
    return;
  }

  state.slots[key].selectedMealId = mealId;
  saveState();
  closeMealDialog(false);
  renderPlanner();
  renderSummaryAndGroceries();
}

function createOptionButton(day, mealTypeId, slot, mealId) {
  const meal = mealById.get(mealId);
  if (!meal) {
    return null;
  }

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'option-chip';
  const isSelected = slot.selectedMealId === meal.id;
  button.setAttribute(
    'aria-label',
    `${meal.name}. ${mealTypeLabel(mealTypeId)} for ${day}. Tap to view ingredients and add to weekly menu.`,
  );
  if (isSelected) {
    button.classList.add('selected');
  }

  const name = document.createElement('span');
  name.className = 'option-name';
  name.textContent = meal.name;

  const meta = document.createElement('span');
  meta.className = 'option-meta';
  meta.textContent = `${formatCurrency(mealCostForFamily(meal))} per family | ${mealTagLabel(meal)}`;

  button.append(name, meta);

  button.addEventListener('click', () => {
    openMealDialog(day, mealTypeId, meal.id, button);
  });

  return button;
}

function renderPlanner() {
  ui.planner.innerHTML = '';

  for (const day of DAYS) {
    const dayCard = document.createElement('article');
    dayCard.className = 'day-card';

    const title = document.createElement('h3');
    title.className = 'day-title';
    title.textContent = day;
    dayCard.appendChild(title);

    for (const mealType of MEAL_TYPES) {
      const key = slotKey(day, mealType.id);
      const slot = state.slots[key];

      const slotSection = document.createElement('section');
      slotSection.className = 'slot';

      const slotHead = document.createElement('div');
      slotHead.className = 'slot-head';

      const slotTitle = document.createElement('h3');
      slotTitle.textContent = mealType.label;

      const reSuggestButton = document.createElement('button');
      reSuggestButton.type = 'button';
      reSuggestButton.className = 'resuggest';
      reSuggestButton.textContent = 'Re-suggest';
      reSuggestButton.setAttribute('aria-label', `Re-suggest ${mealType.label} for ${day}`);
      reSuggestButton.addEventListener('click', () => {
        regenerateSingleSlot(day, mealType.id);
        renderPlanner();
        renderSummaryAndGroceries();
      });

      slotHead.append(slotTitle, reSuggestButton);

      const optionList = document.createElement('div');
      optionList.className = 'option-list';

      if (!slot?.suggestionIds?.length) {
        const empty = document.createElement('p');
        empty.className = 'empty-note';
        empty.textContent = 'No suggestions available for this slot.';
        optionList.appendChild(empty);
      } else {
        for (const mealId of slot.suggestionIds) {
          const button = createOptionButton(day, mealType.id, slot, mealId);
          if (button) {
            optionList.appendChild(button);
          }
        }
      }

      slotSection.append(slotHead, optionList);
      dayCard.appendChild(slotSection);
    }

    ui.planner.appendChild(dayCard);
  }
}

function selectedMealsGroupedByDay() {
  const grouped = [];

  for (const day of DAYS) {
    const row = { day, meals: {}, dayCost: 0 };

    for (const mealType of MEAL_TYPES) {
      const meal = selectedMealFor(day, mealType.id);
      row.meals[mealType.id] = meal;
      if (meal) {
        row.dayCost += mealCostForFamily(meal);
      }
    }

    grouped.push(row);
  }

  return grouped;
}

function groceryCategoryForIngredient(ingredientName) {
  return INGREDIENT_CATEGORY[ingredientName] || 'other';
}

function aggregateGroceries(groupedMeals) {
  const merged = new Map();

  for (const dayData of groupedMeals) {
    for (const mealType of MEAL_TYPES) {
      const meal = dayData.meals[mealType.id];
      if (!meal) {
        continue;
      }

      for (const ingredient of meal.ingredients) {
        const key = `${ingredient.name}|${ingredient.unit}`;
        const existing = merged.get(key) || {
          name: ingredient.name,
          unit: ingredient.unit,
          quantity: 0,
          estimatedPrice: 0,
        };

        existing.quantity += ingredient.qty * state.settings.familySize;
        merged.set(key, existing);
      }
    }
  }

  const rows = Array.from(merged.values()).map((item) => {
    const priceRef = INGREDIENT_PRICES[item.name];
    if (priceRef && priceRef.unit === item.unit) {
      item.estimatedPrice = item.quantity * priceRef.price;
    } else {
      item.estimatedPrice = 0;
    }
    return item;
  });

  return rows;
}

function groupGroceriesByCategory(groceryRows) {
  const groupsById = new Map(
    GROCERY_CATEGORIES.map((category) => [category.id, {
      id: category.id,
      label: category.label,
      items: [],
      subtotal: 0,
    }]),
  );

  for (const item of groceryRows) {
    const categoryId = groceryCategoryForIngredient(item.name);
    const group = groupsById.get(categoryId) || groupsById.get('other');
    group.items.push(item);
    group.subtotal += item.estimatedPrice;
  }

  const orderedGroups = [];
  for (const category of GROCERY_CATEGORIES) {
    const group = groupsById.get(category.id);
    if (!group || !group.items.length) {
      continue;
    }
    group.items.sort((a, b) => a.name.localeCompare(b.name));
    orderedGroups.push(group);
  }

  return orderedGroups;
}

function formatCurrency(value) {
  return `PHP ${Number(value).toFixed(2)}`;
}

function smartRound(value) {
  if (value >= 100) {
    return value.toFixed(0);
  }
  if (value >= 10) {
    return value.toFixed(1);
  }
  return value.toFixed(2);
}

function formatQuantity(quantity, unit) {
  if (unit === 'g' && quantity >= 1000) {
    return `${smartRound(quantity / 1000)} kg`;
  }
  if (unit === 'ml' && quantity >= 1000) {
    return `${smartRound(quantity / 1000)} L`;
  }
  if (unit === 'pc') {
    return `${smartRound(quantity)} pcs`;
  }
  if (unit === 'can') {
    return `${smartRound(quantity)} cans`;
  }
  return `${smartRound(quantity)} ${unit}`;
}

function renderSummaryAndGroceries() {
  const grouped = selectedMealsGroupedByDay();

  let totalMeals = 0;
  let totalCost = 0;

  ui.summaryTableBody.innerHTML = '';

  for (const dayRow of grouped) {
    const tr = document.createElement('tr');

    const dayCell = document.createElement('td');
    dayCell.textContent = dayRow.day;
    tr.appendChild(dayCell);

    for (const mealType of MEAL_TYPES) {
      const cell = document.createElement('td');
      const meal = dayRow.meals[mealType.id];
      cell.textContent = meal ? meal.name : '--';
      tr.appendChild(cell);
      if (meal) {
        totalMeals += 1;
      }
    }

    totalCost += dayRow.dayCost;

    const costCell = document.createElement('td');
    costCell.textContent = formatCurrency(dayRow.dayCost);
    tr.appendChild(costCell);

    ui.summaryTableBody.appendChild(tr);
  }

  ui.statMeals.textContent = String(totalMeals);
  ui.statWeeklyCost.textContent = formatCurrency(totalCost);
  ui.statDailyCost.textContent = formatCurrency(totalCost / DAYS.length);

  const groceryRows = aggregateGroceries(grouped);
  const groceryGroups = groupGroceriesByCategory(groceryRows);
  ui.groceryTableBody.innerHTML = '';

  let groceryTotal = 0;

  if (!groceryGroups.length) {
    const empty = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 3;
    cell.className = 'empty-note';
    cell.textContent = 'Select meals to generate grocery list.';
    empty.appendChild(cell);
    ui.groceryTableBody.appendChild(empty);
  } else {
    for (const group of groceryGroups) {
      const groupRow = document.createElement('tr');
      groupRow.className = 'grocery-group-row';

      const groupCell = document.createElement('td');
      groupCell.colSpan = 3;
      groupCell.textContent = `${group.label} (Subtotal: ${formatCurrency(group.subtotal)})`;
      groupRow.appendChild(groupCell);
      ui.groceryTableBody.appendChild(groupRow);

      for (const item of group.items) {
        const tr = document.createElement('tr');

        const nameCell = document.createElement('td');
        nameCell.textContent = item.name;

        const qtyCell = document.createElement('td');
        qtyCell.textContent = formatQuantity(item.quantity, item.unit);

        const priceCell = document.createElement('td');
        priceCell.textContent = formatCurrency(item.estimatedPrice);

        tr.append(nameCell, qtyCell, priceCell);
        ui.groceryTableBody.appendChild(tr);

        groceryTotal += item.estimatedPrice;
      }
    }
  }

  ui.groceryTotal.textContent = formatCurrency(groceryTotal);
}

function csvEscape(value) {
  const text = String(value ?? '');
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function exportCsv() {
  const grouped = selectedMealsGroupedByDay();
  const groceries = aggregateGroceries(grouped);
  const groceryGroups = groupGroceriesByCategory(groceries);

  const rows = [];
  rows.push(['Day', 'Breakfast', 'Lunch', 'Dinner', 'Estimated Day Cost PHP']);

  let weeklyTotal = 0;

  for (const dayRow of grouped) {
    const breakfast = dayRow.meals.breakfast?.name || '--';
    const lunch = dayRow.meals.lunch?.name || '--';
    const dinner = dayRow.meals.dinner?.name || '--';
    weeklyTotal += dayRow.dayCost;

    rows.push([
      dayRow.day,
      breakfast,
      lunch,
      dinner,
      dayRow.dayCost.toFixed(2),
    ]);
  }

  rows.push([]);
  rows.push(['Estimated Weekly Menu Cost', weeklyTotal.toFixed(2)]);
  rows.push([]);
  rows.push(['Category / Ingredient', 'Quantity', 'Estimated Price PHP']);

  let groceryTotal = 0;
  for (const group of groceryGroups) {
    rows.push([`${group.label} (Subtotal)`, '', group.subtotal.toFixed(2)]);

    for (const item of group.items) {
      groceryTotal += item.estimatedPrice;
      rows.push([
        item.name,
        formatQuantity(item.quantity, item.unit),
        item.estimatedPrice.toFixed(2),
      ]);
    }

    rows.push([]);
  }

  rows.push(['Estimated Grocery Total', groceryTotal.toFixed(2)]);

  const csv = rows.map((row) => row.map(csvEscape).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  link.download = 'gumaca-weekly-meal-and-grocery-plan.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function resetPlanner() {
  closeMealDialog(false);

  state.settings = {
    familySize: 6,
    budgetMode: 'balanced',
    avoidPork: false,
    avoidSeafood: false,
    preferVegetables: false,
    kidsOnly: false,
  };
  state.slots = {};
  applyStateToInputs();
  regenerateWeek();
  renderPlanner();
  renderSummaryAndGroceries();
}

function bindEvents() {
  ui.generateButton.addEventListener('click', () => {
    closeMealDialog(false);
    readSettingsFromInputs();
    regenerateWeek();
    renderPlanner();
    renderSummaryAndGroceries();
  });

  ui.resetButton.addEventListener('click', () => {
    localStorage.removeItem(STORAGE_KEY);
    resetPlanner();
  });

  ui.exportCsvButton.addEventListener('click', () => {
    exportCsv();
  });

  ui.familySize.addEventListener('change', () => {
    closeMealDialog(false);
    readSettingsFromInputs();
    saveState();
    renderSummaryAndGroceries();
    renderPlanner();
  });

  [ui.budgetMode, ui.avoidPork, ui.avoidSeafood, ui.preferVegetables, ui.kidsOnly]
    .filter(Boolean)
    .forEach((control) => {
    control.addEventListener('change', () => {
      closeMealDialog(false);
      readSettingsFromInputs();
      regenerateWeek();
      renderPlanner();
      renderSummaryAndGroceries();
    });
    });

  if (ui.mealDialogBackdrop) {
    ui.mealDialogBackdrop.addEventListener('click', () => {
      closeMealDialog();
    });
  }

  if (ui.mealDialogClose) {
    ui.mealDialogClose.addEventListener('click', () => {
      closeMealDialog();
    });
  }

  if (ui.mealDialogAdd) {
    ui.mealDialogAdd.addEventListener('click', () => {
      addDialogMealToWeeklyMenu();
    });
  }

  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && ui.mealDialog && !ui.mealDialog.hidden) {
      event.preventDefault();
      closeMealDialog();
    }
  });
}

function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('./sw.js').catch(() => {
        // Fail silently for local file previews.
      });
    });
  }
}

function init() {
  loadState();
  populateFamilySizeOptions();
  applyStateToInputs();

  if (!sanitizeSlots() || !hasCompleteSlots()) {
    regenerateWeek();
  }

  bindEvents();
  renderPlanner();
  renderSummaryAndGroceries();
  registerServiceWorker();
}

init();
