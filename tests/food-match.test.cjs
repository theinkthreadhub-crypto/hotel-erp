// Smart Food Visuals: matching accuracy and wrong-picture prevention (offline, no server)
// node tests/food-match.test.cjs
const FV = require('../food/food-match.js');
const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got });

// [dish name, category, expected picture]. 'cat' = must NOT get a dish picture (placeholder or review only)
const CASES = [
  // the brief's examples
  ['Paneer Butter Masala', 'Main Course', 'paneer-curry'], ['Veg Biryani', 'Rice', 'veg-biryani'], ['Masala Dosa', 'South Indian', 'dosa'],
  ['Butter Naan', 'Breads', 'naan'], ['Cold Coffee', 'Beverages', 'coffee-cold'], ['Margherita Pizza', 'Pizza', 'pizza'],
  // English variety
  ['Kadai Paneer', '', 'paneer-curry'], ['Shahi Paneer (Half)', 'Paneer', 'paneer-curry'], ['Paneer Tikka', 'Starters', 'paneer-tikka'], ['Malai Kofta', '', 'veg-curry'],
  ['Dal Makhani', '', 'dal'], ['Dal Tadka', 'Dal', 'dal'], ['Chole Bhature', '', 'puri'], ['Rajma Chawal', '', 'bean-curry'], ['Butter Chicken', '', 'chicken-curry'],
  ['Chicken Tikka', 'Starters', 'tandoori-chicken'], ['Tandoori Chicken (Full)', '', 'tandoori-chicken'], ['Chicken Biryani', '', 'chicken-biryani'], ['Mutton Biryani', '', 'chicken-biryani'],
  ['Egg Curry', '', 'egg-curry'], ['Mutton Rogan Josh', '', 'mutton-curry'], ['Fish Curry', '', 'fish-curry'], ['Jeera Rice', '', 'rice'], ['Veg Fried Rice', 'Chinese', 'fried-rice'],
  ['Hakka Noodles', 'Chinese', 'noodles'], ['Veg Manchurian', 'Chinese', 'indo-chinese'], ['Chilli Paneer', 'Chinese', 'indo-chinese'], ['Veg Momos', '', 'momos'], ['Spring Roll', '', 'spring-roll'],
  ['Idli Sambar', '', 'idli'], ['Medu Vada', '', 'idli'], ['Tandoori Roti', '', 'roti'], ['Aloo Paratha', '', 'paratha'], ['Laccha Paratha', 'Breads', 'paratha'], ['Samosa', 'Snacks', 'samosa'],
  ['Onion Pakora', '', 'pakora'], ['Pani Puri', '', 'chaat'], ['Pav Bhaji', '', 'pav-bhaji'], ['Vada Pav', '', 'pav-bhaji'], ['Veg Burger', '', 'burger'], ['Grilled Sandwich', '', 'sandwich'],
  ['French Fries', '', 'fries'], ['White Sauce Pasta', '', 'pasta'], ['Tomato Soup', 'Soups', 'soup'], ['Green Salad', '', 'salad'], ['Special Thali', '', 'thali'], ['Boondi Raita', '', 'raita'],
  ['Masala Papad', '', 'papad'], ['Masala Chai', 'Beverages', 'tea'], ['Filter Coffee', '', 'coffee-hot'], ['Cappuccino', '', 'coffee-hot'], ['Sweet Lassi', '', 'lassi'], ['Chocolate Shake', '', 'shake'],
  ['Fresh Lime Soda', '', 'juice'], ['Coke 500ml', '', 'soft-drink'], ['Mineral Water', '', 'water'], ['Vanilla Ice Cream', '', 'ice-cream'], ['Gulab Jamun (2 pcs)', 'Desserts', 'indian-sweet'],
  ['Chocolate Brownie', '', 'cake'], ['Chicken 65', '', 'tandoori-chicken'], ['Chicken Chowmein', '', 'noodles'], ['Egg Fried Rice', '', 'fried-rice'], ['Kathi Roll', '', 'sandwich'],
  // Hindi (Devanagari) and mixed
  ['पनीर बटर मसाला', '', 'paneer-curry'], ['वेज बिरयानी', '', 'veg-biryani'], ['मसाला डोसा', '', 'dosa'], ['बटर नान', '', 'naan'], ['कोल्ड कॉफी', '', 'coffee-cold'], ['पिज़्ज़ा', '', 'pizza'],
  ['दाल मखनी', '', 'dal'], ['छोले भटूरे', '', 'puri'], ['चिकन बिरयानी', '', 'chicken-biryani'], ['तंदूरी रोटी', '', 'roti'], ['आलू पराठा', '', 'paratha'], ['समोसा', '', 'samosa'], ['मसाला चाय', '', 'tea'],
  ['गुलाब जामुन', '', 'indian-sweet'], ['पाव भाजी', '', 'pav-bhaji'], ['पनीर टिक्का', '', 'paneer-tikka'], ['मोमोज', '', 'momos'], ['लस्सी', '', 'lassi'], ['पनीर tikka', '', 'paneer-tikka'],
  ['Paneer बटर masala', '', 'paneer-curry'], ['दाल तड़का', '', 'dal'], ['बिरियानी वेज', '', 'veg-biryani'],
  // spelling mistakes, short forms, punctuation, case
  ['PANEER BUTTER MASALA', '', 'paneer-curry'], ['paneer-butter-masala', '', 'paneer-curry'], ['Panner Butter Masala', '', 'paneer-curry'], ['Paner Buter Masala', '', 'paneer-curry'],
  ['PBM', '', 'paneer-curry'], ['Veg Biriyani', '', 'veg-biryani'], ['Veg. Briyani', '', 'veg-biryani'], ['Masaala Dosa', '', 'dosa'], ['Masala Dhosa', '', 'dosa'], ['Buttor Naan', '', 'naan'],
  ['Cold Cofee', '', 'coffee-cold'], ['Coffe Cold', '', 'coffee-cold'], ['Margarita Pizza', '', 'pizza'], ['Piza Margherita', '', 'pizza'], ['Chiken Biryani', '', 'chicken-biryani'],
  ['Chk Tikka', '', 'tandoori-chicken'], ['Dal Makhni', '', 'dal'], ['Chhole Bhature', '', 'puri'], ['Gulabjamun', '', 'indian-sweet'], ['Sandwhich Grilled', '', 'sandwich'], ['Veg Shezwan Noodles', '', 'noodles'],
  ['Manchuria Dry', '', 'indo-chinese'], ['Chilly Chicken', '', 'indo-chinese'], ['Capuccino', '', 'coffee-hot'], ['Pav-Bhaji (Butter)', '', 'pav-bhaji'], ['  masala   dosa  ', '', 'dosa'],
  // must NOT get a wrong dish picture (placeholder / review only)
  ['Fish Fry', '', 'fish-fry'], ['Aloo Fry', '', 'cat'], ['Naan Khatai', '', 'cat'], ['Butter Milk', '', 'lassi'], ['Paan', '', 'cat'], ['Meetha Paan', '', 'cat'],
  ['Packing Charges', '', 'cat'], ['Service Charge', '', 'cat'], ['Extra Cheese', '', 'cat'], ['Combo 1', '', 'cat'], ['Today Special', '', 'cat'], ['Chef Special', 'Main Course', 'cat'],
  ['XYZ Delight', '', 'cat'], ['Hotel Room Tariff', '', 'cat'], ['Paneer', '', 'cat'], ['Chicken', '', 'cat'], ['Masala', '', 'cat'], ['Butter', '', 'cat'],
  ['Watermelon Juice', '', 'juice'], ['Pan Cake', '', 'cake'], ['Pizza Sauce Dip', '', 'pizza'], ['Ice Tea', '', 'juice']
];
// Pairs that must never be confused (wrong-picture prevention)
const NEVER = [
  ['Chicken Biryani', 'veg-biryani'], ['Mutton Biryani', 'veg-biryani'], ['Egg Biryani', 'veg-biryani'], ['Paneer Biryani', 'chicken-biryani'], ['Veg Biryani', 'chicken-biryani'],
  ['Paneer Tikka', 'tandoori-chicken'], ['Chicken Tikka', 'paneer-tikka'], ['Paneer Butter Masala', 'chicken-curry'], ['Butter Chicken', 'paneer-curry'],
  ['Cold Coffee', 'coffee-hot'], ['Hot Coffee', 'coffee-cold'], ['Masala Chai', 'dosa'], ['Masala Dosa', 'tea'], ['Fish Fry', 'fries'], ['Aloo Fry', 'fries'],
  ['Naan Khatai', 'naan'], ['Butter Milk', 'naan'], ['Butter Milk', 'paneer-curry'], ['Paan', 'paneer-curry'], ['Pani Puri', 'puri'], ['Pani Puri', 'water'], ['Chilli Chicken', 'chicken-curry'],
  ['Veg Fried Rice', 'rice'], ['Chicken Fried Rice', 'chicken-biryani'], ['Egg Curry', 'veg-curry'], ['Veg Manchurian', 'chicken-curry'], ['Chicken Soup', 'chicken-curry'], ['Paneer Pizza', 'paneer-curry'],
  ['Paneer Roll', 'paneer-curry'], ['Paneer Paratha', 'paneer-curry'], ['Chicken Burger', 'chicken-curry'], ['Chicken Momos', 'chicken-curry'], ['Dahi Puri', 'raita'], ['Dahi Vada', 'idli']
];

let right = 0, wrong = 0, missed = 0;
const fails = [];
for(const [n, c, want] of CASES){
  const r = FV.match(n, c);
  const shown = r.status === 'matched' ? r.img : 'cat';
  if(shown === want) right++;
  else if(want === 'cat' || (shown !== 'cat' && shown !== want)) { wrong++; fails.push(`WRONG ${n} [${c}] -> ${r.img} ${r.status} ${r.conf} (want ${want})`); }
  else { missed++; fails.push(`MISS  ${n} [${c}] -> ${r.img} ${r.status} ${r.conf} (want ${want})`); }
}
t(`Known dishes shown with the right picture: ${right}/${CASES.length}`, right / CASES.length >= 0.95, fails);
if(process.env.SHOW) console.log(fails.join('\n'));
t('No dish ever shown with a wrong picture (matched status)', wrong === 0, fails.filter(f => f.startsWith('WRONG')));
const conf = NEVER.filter(([n, img]) => { const r = FV.match(n, ''); return (r.status === 'matched' || r.status === 'review') && r.img === img; });
t(`Never-confuse pairs: ${NEVER.length - conf.length}/${NEVER.length}`, conf.length === 0, conf);

// Unknown dishes get a category placeholder, chosen by the menu's category
const u1 = FV.match('XYZ Delight', 'Desserts'), u2 = FV.match('House Blend No 5', 'Beverages'), u3 = FV.match('Grandma Recipe', '');
t('Unknown dish → category placeholder (dessert / beverage / generic)', u1.img === 'cat-dessert' && u2.img === 'cat-beverage' && u3.img === 'cat-generic' && u1.status === 'placeholder', [u1, u2, u3]);
// Category as secondary information: a dessert category does not take a main-course picture with high confidence
const cm = FV.match('Paneer Butter Masala', 'Desserts');
t('Category disagreement lowers confidence to review', cm.status !== 'matched' || cm.conf < 0.8, cm);

// Priority: upload > link > chosen > auto > placeholder
const P = FV.pick;
const m = { id: 'x', name: 'Veg Biryani', cat: 'Rice' };
t('Auto picture when nothing is set', P(m).src === 'veg-biryani' && P(m).kind === 'auto', P(m));
t('Owner-chosen library picture wins over auto', P({ ...m, lib: 'rice' }).src === 'rice', P({ ...m, lib: 'rice' }));
t('https link wins over chosen', P({ ...m, lib: 'rice', img: 'https://x.example/a.jpg' }).kind === 'link');
t('Own upload wins over everything', P({ ...m, lib: 'rice', img: 'https://x.example/a.jpg', photo: 'm_0123456789abcdef0123456789abcdef' }).kind === 'custom');
t('"No picture" choice shows the category placeholder', P({ ...m, lib: 'none' }).kind === 'category');
t('Review-level match shows the placeholder (with a suggestion), not the guess', (() => { const r = P({ id: 'y', name: 'Paneer Butter Masala', cat: 'Desserts' }); return r.kind !== 'auto'; })());

// Speed: 1,000 dish names well under a second (cached afterwards)
const names = []; for(let i = 0; i < 1000; i++) names.push(CASES[i % CASES.length][0] + (i >= CASES.length ? ' ' + (i % 7 ? 'Half' : 'Spl') : ''));
let t0 = process.hrtime.bigint(); names.forEach(n => FV.match(n + ' #' + Math.random().toString(36).slice(2, 4), '')); const ms = Number(process.hrtime.bigint() - t0) / 1e6;
t(`1,000 uncached matches in ${ms.toFixed(0)} ms (< 1500)`, ms < 1500, ms);

let fail = 0;
for(const r of R){ if(!r.ok) fail++; console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : '\n  ' + String(JSON.stringify(r.got, null, 1)).slice(0, 3000))); }
console.log(`\n${R.length - fail}/${R.length} passed`);
process.exit(fail ? 1 : 0);
