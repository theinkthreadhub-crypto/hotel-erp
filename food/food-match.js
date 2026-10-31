/* Smart Food Visuals: dish-name → library image matcher. Works offline, no network.
 * Plain script: in the page it sets window.FoodVisuals; in Node / the Worker it sets globalThis.FoodVisuals
 * (and module.exports under CommonJS).
 *
 * match(name, category) → { img, dish, conf, status, kind }
 *   status: 'matched' (conf ≥ 0.80, shown everywhere) · 'review' (0.55–0.80, owner should confirm; shown as the
 *           category placeholder until confirmed) · 'placeholder' (no dish found: category or generic picture)
 *   kind:   'dish' · 'category' · 'generic'
 * Rule: a dish picture is only chosen from the dish's own words. Never a random or "closest-looking" dish.
 */
(function(root){
  'use strict';

  // ---------- library: one picture serves several dishes (dedupe) ----------
  // Picture ids are file names in food/lib/<id>.webp and food/thumb/<id>.webp
  const CATS = {
    starter: 'Starters', main: 'Main course', bread: 'Breads', rice: 'Rice', chinese: 'Chinese',
    south: 'South Indian', snacks: 'Snacks', beverage: 'Beverages', dessert: 'Desserts', fastfood: 'Fast food',
    soup: 'Soups & salads', generic: 'Dish'
  };
  // Category words in the menu's own category (or dish name) → category placeholder
  const CAT_WORDS = {
    starter: ['starter', 'starters', 'appetizer', 'appetizers', 'tandoor', 'tandoori', 'kebab', 'kabab', 'tikka'],
    main: ['main', 'maincourse', 'curry', 'curries', 'gravy', 'sabji', 'sabzi', 'subzi', 'paneer', 'veg', 'nonveg', 'chicken', 'mutton', 'dal', 'thali', 'special', 'fish', 'prawn', 'prawns', 'seafood', 'kadhi'],
    bread: ['bread', 'breads', 'roti', 'rotis', 'naan', 'paratha', 'parathe', 'kulcha', 'tandoorbread'],
    rice: ['rice', 'biryani', 'pulao', 'pulav'],
    chinese: ['chinese', 'indochinese', 'oriental', 'noodles', 'momos', 'momo'],
    south: ['south', 'southindian', 'dosa', 'idli', 'uttapam'],
    snacks: ['snack', 'snacks', 'chaat', 'nashta', 'breakfast', 'evening'],
    beverage: ['beverage', 'beverages', 'drink', 'drinks', 'shake', 'shakes', 'juice', 'juices', 'tea', 'coffee', 'mocktail', 'mocktails', 'cold', 'hot', 'lassi'],
    dessert: ['dessert', 'desserts', 'sweet', 'sweets', 'mithai', 'icecream', 'cake', 'cakes', 'bakery'],
    fastfood: ['fastfood', 'pizza', 'pizzas', 'burger', 'burgers', 'sandwich', 'sandwiches', 'pasta', 'continental', 'italian'],
    soup: ['soup', 'soups', 'salad', 'salads']
  };

  // ---------- dictionary ----------
  // id: canonical dish family · img: picture · cat: category placeholder for the family
  // names: full names (any word order is fine) · keys: words that on their own name the family
  // need: at least one of these words must be in the name · avoid: none of these may be in the name
  // meat: true when the family is non-veg (a veg name never gets it); veg: hint only, never shown as verified
  const DISH = [
    { id: 'paneer-curry', img: 'paneer-curry', cat: 'main', veg: true, names: ['paneer butter masala', 'shahi paneer', 'kadai paneer', 'kadhai paneer', 'paneer tikka masala', 'matar paneer', 'palak paneer', 'paneer lababdar', 'paneer do pyaza', 'paneer makhani', 'paneer handi', 'paneer pasanda', 'paneer kolhapuri', 'paneer bhurji', 'paneer masala', 'paneer curry', 'pbm', 'paneer korma', 'paneer jalfrezi', 'paneer kali mirch', 'paneer khurchan', 'paneer mughlai', 'paneer angara'], need: ['paneer'], assist: true, avoid: ['tikka', 'chilli', 'pakora', 'roll', 'pizza', 'sandwich', 'biryani', 'paratha', 'momos', 'manchurian', 'fried', 'soup', 'salad', 'dosa', 'burger', 'kulcha', 'naan'], keysIfNeed: ['masala', 'curry', 'makhani', 'butter', 'kadai', 'kadhai', 'shahi', 'palak', 'matar', 'handi', 'lababdar', 'bhurji', 'pasanda', 'kofta', 'korma', 'gravy'] },
    { id: 'paneer-tikka', img: 'paneer-tikka', cat: 'starter', veg: true, names: ['paneer tikka', 'achari paneer tikka', 'malai paneer tikka', 'tandoori paneer', 'paneer shashlik', 'hariyali paneer tikka', 'tandoori mushroom', 'mushroom tikka', 'tandoori aloo', 'tandoori broccoli', 'soya chaap tikka', 'tandoori soya chaap', 'veg tikka', 'tandoori gobi'], avoid: ['masala', 'pizza', 'roll', 'sandwich', 'biryani', 'butter', 'chicken', 'fish', 'prawn', 'mutton'] },
    { id: 'veg-curry', img: 'veg-curry', cat: 'main', veg: true, names: ['mix veg', 'mixed veg', 'mix vegetable', 'veg kolhapuri', 'veg jalfrezi', 'veg kadai', 'veg handi', 'malai kofta', 'veg kofta', 'navratan korma', 'veg korma', 'aloo gobi', 'aloo matar', 'dum aloo', 'jeera aloo', 'bhindi masala', 'baingan bharta', 'kaju curry', 'kaju masala', 'mushroom masala', 'mushroom do pyaza', 'methi malai matar', 'sev tamatar', 'aloo sabzi', 'mix veg curry', 'veg curry', 'bhindi do pyaza', 'gobi matar', 'soya chaap masala', 'chaap masala'], assist: true, assistKeys: ['masala', 'curry', 'kadai', 'kadhai', 'handi', 'kolhapuri', 'jalfrezi', 'korma', 'kofta', 'bharta', 'sabzi', 'pyaza', 'lababdar', 'makhani', 'malai', 'kali', 'mughlai', 'hyderabadi', 'angara', 'saagwala', 'achari', 'bhuna', 'rara'], avoid: ['chicken', 'mutton', 'egg', 'fish', 'biryani', 'pulao', 'rice', 'soup', 'pizza', 'sandwich', 'burger', 'paratha', 'roll', 'momos', 'noodles', 'pakora', 'fry', 'fried', 'manchurian', 'chilli', 'salad', 'samosa', 'tikki', 'uttapam', 'dosa', 'idli', 'sauce', 'bean', 'kung', 'paneer', 'tikka', 'tandoori'] },
    { id: 'bean-curry', img: 'bean-curry', cat: 'main', veg: true, names: ['chole', 'chana masala', 'chole masala', 'pindi chole', 'rajma', 'rajma masala', 'rajma chawal', 'chole chawal', 'amritsari chole', 'chhole', 'kabuli chana', 'black chana', 'kala chana', 'black chana curry', 'lobia', 'lobia masala', 'punjabi chole'], avoid: ['bhature', 'bhatura', 'kulche', 'kulcha', 'samosa', 'tikki', 'chaat', 'puri', 'poori'] },
    { id: 'dal', img: 'dal', cat: 'main', veg: true, names: ['dal makhani', 'dal tadka', 'dal fry', 'yellow dal', 'dal tadka fry', 'moong dal', 'masoor dal', 'toor dal', 'arhar dal', 'dal palak', 'dal bukhara', 'dal makhni', 'daal', 'dal', 'kadhi', 'kadhi pakora', 'sambar'], need: ['dal', 'daal', 'kadhi', 'sambar'], avoid: ['bati', 'baati', 'khichdi', 'rice', 'chawal', 'paratha', 'pakwan', 'halwa', 'soup', 'vada', 'idli', 'dosa'] },
    { id: 'chicken-curry', img: 'chicken-curry', cat: 'main', meat: true, names: ['butter chicken', 'chicken butter masala', 'chicken tikka masala', 'kadai chicken', 'kadhai chicken', 'chicken curry', 'chicken masala', 'chicken korma', 'chicken handi', 'chicken do pyaza', 'murgh makhani', 'chicken makhani', 'chicken lababdar', 'chicken kolhapuri', 'chicken chettinad', 'chicken rogan josh', 'home style chicken', 'chicken bharta'], need: ['chicken', 'murgh', 'murg'], assist: true, avoid: ['tikka', 'tandoori', 'kebab', 'biryani', 'fried', 'rice', 'noodles', 'soup', 'momos', 'roll', 'pizza', 'burger', 'sandwich', 'lollipop', 'chilli', 'manchurian', 'wings', 'pakora', 'seekh', 'malai', 'reshmi', 'afghani'], keysIfNeed: ['curry', 'masala', 'butter', 'kadai', 'kadhai', 'korma', 'handi', 'makhani', 'gravy', 'lababdar'] },
    { id: 'mutton-curry', img: 'mutton-curry', cat: 'main', meat: true, names: ['mutton curry', 'mutton rogan josh', 'rogan josh', 'mutton korma', 'mutton masala', 'laal maas', 'mutton handi', 'mutton do pyaza', 'keema', 'mutton keema', 'keema matar', 'nalli nihari', 'nihari', 'bhuna gosht', 'gosht', 'mutton kadai'], assist: true, need: ['mutton', 'gosht', 'keema', 'lamb', 'rogan', 'nihari', 'laal', 'maas'], avoid: ['biryani', 'kebab', 'seekh', 'soup', 'roll', 'samosa', 'pav', 'paratha', 'pulao', 'rice', 'tikka', 'fry'] },
    { id: 'egg-curry', img: 'egg-curry', cat: 'main', meat: true, assist: true, names: ['egg curry', 'anda curry', 'egg masala', 'egg bhurji', 'anda bhurji', 'egg kadai', 'egg korma'], need: ['egg', 'anda', 'eggs'], avoid: ['rice', 'noodles', 'roll', 'biryani', 'paratha', 'sandwich', 'burger', 'omelette', 'omelet', 'boiled', 'maggi'] },
    { id: 'fish-curry', img: 'fish-curry', cat: 'main', meat: true, assist: true, names: ['fish curry', 'fish masala', 'goan fish curry', 'fish goan curry', 'prawn curry', 'prawns masala', 'prawn masala', 'fish moilee', 'machli curry', 'macher jhol', 'fish tikka masala', 'prawn tikka masala', 'fish malabari curry', 'prawn coconut curry', 'fish amritsari curry'], need: ['fish', 'prawn', 'prawns', 'machli', 'macher', 'pomfret', 'surmai', 'rawas', 'jhinga'], avoid: ['finger', 'fingers', 'chips', 'biryani', 'rice', 'soup', 'roll', 'burger', 'tikka', 'fry', 'amritsari', 'tandoori', 'chilli', 'schezwan', 'garlic', 'pepper', 'salt', 'noodles', 'tempura', 'sauce', 'gravy', 'pizza'], keysIfNeed: ['curry', 'masala', 'kadai', 'butter', 'malabari', 'chettinad', 'mustard', 'goan', 'moilee', 'jhol', 'mughlai', 'kali'] },
    { id: 'fish-fry', img: 'fish-fry', cat: 'starter', meat: true, names: ['fish fry', 'fish tikka', 'fish tawa fry', 'tawa fish', 'amritsari fish', 'fish amritsari', 'tandoori fish', 'prawn tikka', 'prawns fry', 'prawn fry', 'prawn pepper fry', 'fish finger', 'fish fingers', 'fried fish', 'rawa fish fry', 'tandoori prawns', 'prawn tempura', 'crispy garlic prawns'], need: ['fish', 'prawn', 'prawns', 'machli', 'pomfret', 'surmai', 'jhinga'], avoid: ['masala', 'curry', 'chilli', 'salt', 'schezwan', 'soup', 'biryani', 'rice', 'noodles'] },
    { id: 'tandoori-chicken', img: 'tandoori-chicken', cat: 'starter', meat: true, names: ['tandoori chicken', 'chicken tikka', 'chicken malai tikka', 'malai tikka', 'afghani chicken', 'chicken angara', 'tangdi kebab', 'chicken tangdi', 'chicken kebab', 'boti kebab', 'chicken lollipop', 'chicken wings', 'kalmi kebab', 'chicken 65', 'chicken 65 dry', 'chicken drumsticks', 'chicken achari tikka', 'chicken hariyali tikka', 'chicken afghani tikka'], need: ['chicken', 'murgh', 'murg', 'tangdi', 'boti', 'kalmi', 'wings', 'lollipop'], avoid: ['masala', 'curry', 'biryani', 'roll', 'pizza', 'butter', 'rice', 'paneer', 'veg', 'hara', 'soup'], keysIfNeed: ['tandoori', 'tikka', 'kebab', 'kabab', 'seekh', 'tangdi', 'malai', 'reshmi', 'afghani', 'angara', 'lollipop', 'wings'] },
    { id: 'kebab', img: 'kebab', cat: 'starter', meat: true, names: ['seekh kebab', 'chicken seekh kebab', 'mutton seekh kebab', 'shami kebab', 'mutton shami kebab', 'galouti kebab', 'mutton galouti kebab', 'reshmi kebab', 'chicken reshmi kebab', 'kakori kebab', 'mutton kebab', 'lamb seekh'], need: ['seekh', 'shami', 'galouti', 'reshmi', 'kakori', 'kebab', 'kabab'], avoid: ['roll', 'biryani', 'paratha', 'tangdi', 'boti', 'hara', 'dahi', 'veg', 'paneer'] },
    { id: 'veg-kebab', img: 'veg-kebab', cat: 'starter', veg: true, names: ['hara bhara kebab', 'dahi ke kebab', 'dahi kebab', 'veg seekh kebab', 'veg kebab', 'veg cutlet', 'cutlet', 'aloo tikki', 'corn tikki', 'soya kebab', 'beetroot tikki', 'rajma galouti'], avoid: ['burger', 'chaat', 'chicken', 'mutton', 'fish'] },
    { id: 'veg-biryani', img: 'veg-biryani', cat: 'rice', veg: true, names: ['veg biryani', 'vegetable biryani', 'paneer biryani', 'hyderabadi veg biryani', 'veg dum biryani', 'subz biryani', 'mushroom biryani', 'kathal biryani', 'jackfruit biryani', 'soya biryani', 'soya chaap biryani', 'biryani'], need: ['biryani', 'biriyani', 'briyani', 'biryanee'], avoid: ['chicken', 'mutton', 'egg', 'fish', 'prawn', 'prawns', 'keema', 'gosht', 'murgh', 'lamb', 'nonveg'] },
    { id: 'chicken-biryani', img: 'chicken-biryani', cat: 'rice', meat: true, names: ['chicken biryani', 'mutton biryani', 'egg biryani', 'hyderabadi chicken biryani', 'chicken dum biryani', 'lucknowi biryani', 'keema biryani', 'fish biryani', 'prawn biryani', 'murgh biryani', 'non veg biryani', 'nonveg biryani', 'gosht biryani'], need: ['biryani', 'biriyani', 'briyani'], needMeat: true },
    { id: 'rice', img: 'rice', cat: 'rice', veg: true, names: ['jeera rice', 'steamed rice', 'plain rice', 'veg pulao', 'peas pulao', 'matar pulao', 'kashmiri pulao', 'ghee rice', 'lemon rice', 'curd rice', 'dal khichdi', 'khichdi', 'pulao', 'pulav', 'basmati rice', 'tomato rice', 'masala rice', 'dal chawal', 'rice bowl', 'veg tahri', 'tahri', 'tehri', 'coconut rice', 'saffron rice'], avoid: ['fried', 'chicken', 'egg', 'schezwan', 'szechwan', 'biryani', 'paper', 'kheer', 'idli', 'dosa', 'noodles', 'manchurian', 'rajma', 'chole', 'flakes'] },
    { id: 'fried-rice', img: 'fried-rice', cat: 'chinese', names: ['veg fried rice', 'fried rice', 'schezwan fried rice', 'egg fried rice', 'chicken fried rice', 'triple schezwan rice', 'schezwan rice', 'burnt garlic rice', 'paneer fried rice', 'singapore rice', 'hakka rice'], need: ['rice'], keysIfNeed: ['fried', 'schezwan', 'szechwan', 'hakka', 'singapore', 'garlic'] },
    { id: 'noodles', img: 'noodles', cat: 'chinese', names: ['veg noodles', 'hakka noodles', 'chowmein', 'chow mein', 'veg chowmein', 'schezwan noodles', 'chilli garlic noodles', 'chicken noodles', 'egg noodles', 'chicken chowmein', 'singapore noodles', 'pad thai', 'ramen', 'maggi', 'masala maggi', 'cheese maggi', 'noodles', 'chopsuey', 'american chopsuey', 'chinese chopsuey', 'chop suey'], avoid: ['soup'] },
    { id: 'indo-chinese', img: 'indo-chinese', cat: 'chinese', names: ['veg manchurian', 'gobi manchurian', 'manchurian', 'chilli paneer', 'paneer chilli', 'chilli chicken', 'chicken chilli', 'chilli potato', 'honey chilli potato', 'chicken manchurian', 'chilli mushroom', 'crispy corn', 'chilli baby corn', 'dragon chicken', 'paneer 65', 'gobi 65', 'chilli gobi', 'paneer manchurian', 'mushroom manchurian', 'chilli fish', 'schezwan paneer', 'chicken schezwan', 'salt and pepper', 'pepper salt', 'kung pao', 'hot garlic sauce', 'black pepper sauce', 'hong kong sauce', 'schezwan gravy', 'chilli gravy', 'chilli dry', 'prawn chilli', 'egg chilli', 'crispy honey chicken', 'honey chicken', 'garlic pepper', 'schezwan dry', 'crispy vegetables', 'schezwan balls', 'crispy lotus stem', 'tofu chilli', 'black bean sauce', 'chicken dragon', 'dragon chicken'], avoid: ['rice', 'noodles', 'soup', 'momos', 'pizza', 'roll', 'sandwich', 'chowmein', 'naan', 'paratha', 'chopsuey', 'idli', 'dosa', 'toast'] },
    { id: 'momos', img: 'momos', cat: 'chinese', names: ['veg momos', 'chicken momos', 'paneer momos', 'steam momos', 'steamed momos', 'fried momos', 'tandoori momos', 'kurkure momos', 'momos', 'momo', 'dimsum', 'dim sum', 'dumplings'] },
    { id: 'spring-roll', img: 'spring-roll', cat: 'chinese', names: ['spring roll', 'veg spring roll', 'chicken spring roll', 'spring rolls', 'dragon roll', 'veg dragon roll', 'cigar roll'] },
    { id: 'dosa', img: 'dosa', cat: 'south', veg: true, names: ['masala dosa', 'plain dosa', 'mysore masala dosa', 'paper dosa', 'rava dosa', 'onion dosa', 'cheese dosa', 'paneer dosa', 'ghee roast dosa', 'set dosa', 'butter masala dosa', 'onion rava dosa', 'mysore dosa', 'paper masala dosa', 'dosa', 'dosai'], need: ['dosa', 'dosai', 'dose', 'dhosa'] },
    { id: 'idli', img: 'idli', cat: 'south', veg: true, names: ['idli', 'idli sambar', 'idly', 'rava idli', 'button idli', 'idli vada', 'medu vada', 'vada sambar', 'sambar vada', 'mendu vada', 'uttapam', 'onion uttapam', 'tomato uttapam', 'mix uttapam', 'appam', 'upma'], avoid: ['pav', 'dahi', 'fry', 'manchurian', 'chilli'] },
    { id: 'naan', img: 'naan', cat: 'bread', veg: true, names: ['butter naan', 'garlic naan', 'plain naan', 'cheese naan', 'garlic butter naan', 'kashmiri naan', 'keema naan', 'stuffed naan', 'naan', 'kulcha', 'amritsari kulcha', 'butter kulcha', 'onion kulcha', 'paneer kulcha', 'aloo kulcha', 'masala kulcha'], need: ['naan', 'nan', 'kulcha', 'kulche'], avoid: ['khatai', 'chole', 'pizza'] },
    { id: 'roti', img: 'roti', cat: 'bread', veg: true, names: ['tandoori roti', 'butter roti', 'plain roti', 'tawa roti', 'chapati', 'chapatti', 'phulka', 'missi roti', 'rumali roti', 'makki ki roti', 'tandoori butter roti', 'roti', 'bajra roti', 'jowar roti'], avoid: ['canai', 'roll', 'pizza'] },
    { id: 'paratha', img: 'paratha', cat: 'bread', veg: true, names: ['aloo paratha', 'paneer paratha', 'gobi paratha', 'laccha paratha', 'lachha paratha', 'mix paratha', 'onion paratha', 'methi paratha', 'plain paratha', 'pudina paratha', 'tawa paratha', 'mooli paratha', 'paratha', 'parantha', 'parotta', 'thepla'], need: ['paratha', 'parantha', 'parotha', 'parotta', 'prantha', 'thepla'] },
    { id: 'puri', img: 'puri', cat: 'bread', veg: true, names: ['chole bhature', 'chhole bhature', 'bhatura', 'bhature', 'puri bhaji', 'poori bhaji', 'aloo puri', 'aloo poori', 'puri sabzi', 'poori', 'puri', 'chole kulche', 'luchi'], avoid: ['pani', 'sev', 'dahi', 'bhel', 'golgappa', 'papdi', 'chaat'] },
    { id: 'samosa', img: 'samosa', cat: 'snacks', veg: true, names: ['samosa', 'aloo samosa', 'punjabi samosa', 'samosa chaat', 'kachori', 'pyaz kachori', 'dal kachori', 'khasta kachori', 'samose'] },
    { id: 'pakora', img: 'pakora', cat: 'snacks', names: ['pakora', 'pakoda', 'onion pakora', 'veg pakora', 'paneer pakora', 'mix pakora', 'bhajiya', 'bhaji', 'onion bhaji', 'aloo bonda', 'batata vada', 'mirchi bada', 'mirchi vada', 'chicken pakora', 'pakode', 'pakore'], avoid: ['kadhi', 'pav', 'puri', 'poori', 'pao'] },
    { id: 'chaat', img: 'chaat', cat: 'snacks', veg: true, names: ['pani puri', 'golgappa', 'gol gappa', 'puchka', 'bhel puri', 'bhel', 'sev puri', 'dahi puri', 'papdi chaat', 'aloo tikki chaat', 'dahi bhalla', 'dahi vada', 'raj kachori', 'chaat', 'ragda pattice', 'tikki chaat'], avoid: ['burger', 'chinese'] },
    { id: 'pav-bhaji', img: 'pav-bhaji', cat: 'snacks', veg: true, names: ['pav bhaji', 'butter pav bhaji', 'cheese pav bhaji', 'pao bhaji', 'vada pav', 'wada pav', 'misal pav', 'dabeli', 'keema pav', 'bhaji pav'] },
    { id: 'pizza', img: 'pizza', cat: 'fastfood', names: ['margherita pizza', 'margarita pizza', 'farmhouse pizza', 'paneer pizza', 'veg pizza', 'cheese pizza', 'chicken pizza', 'pepperoni pizza', 'tandoori paneer pizza', 'corn pizza', 'onion pizza', 'veggie pizza', 'pizza', 'pizzas', 'margherita', 'peppy paneer pizza'], need: ['pizza', 'piza', 'pizaa', 'pizzas', 'margherita', 'margarita'] },
    { id: 'burger', img: 'burger', cat: 'fastfood', names: ['veg burger', 'aloo tikki burger', 'cheese burger', 'chicken burger', 'paneer burger', 'crispy veg burger', 'zinger burger', 'burger', 'burgers', 'veg burgers'] },
    { id: 'sandwich', img: 'sandwich', cat: 'fastfood', names: ['veg sandwich', 'grilled sandwich', 'cheese sandwich', 'club sandwich', 'bombay sandwich', 'paneer sandwich', 'chicken sandwich', 'corn sandwich', 'cheese grilled sandwich', 'sandwich', 'sandwiches', 'toast sandwich', 'sub', 'panini', 'frankie', 'kathi roll', 'paneer roll', 'chicken roll', 'veg roll', 'egg roll', 'wrap', 'shawarma', 'chicken shawarma'], need: ['sandwich', 'sandwiches', 'sandwhich', 'sandwitch', 'panini', 'sub', 'frankie', 'roll', 'wrap', 'shawarma', 'shawarama'], avoid: ['spring', 'rumali', 'dragon', 'cigar', 'sushi'] },
    { id: 'fries', img: 'fries', cat: 'fastfood', veg: true, names: ['french fries', 'salted fries', 'peri peri fries', 'masala fries', 'cheese fries', 'finger chips', 'potato fries', 'fries', 'potato wedges', 'wedges'], need: ['fries', 'chips', 'wedges'], avoid: ['fish'] },
    { id: 'pasta', img: 'pasta', cat: 'fastfood', names: ['white sauce pasta', 'red sauce pasta', 'pink sauce pasta', 'arrabiata pasta', 'arrabbiata', 'alfredo pasta', 'penne pasta', 'mac and cheese', 'spaghetti', 'pasta', 'macaroni', 'pesto pasta'] },
        { id: 'tomato-soup', img: 'tomato-soup', cat: 'soup', veg: true, names: ['tomato soup', 'cream of tomato soup', 'roasted tomato soup', 'veg tomato soup'], need: ['tomato', 'soup'] },
    { id: 'sweet-corn-soup', img: 'sweet-corn-soup', cat: 'soup', names: ['sweet corn soup', 'veg sweet corn soup', 'sweet corn chicken soup', 'corn soup'], need: ['corn', 'soup'] },
    { id: 'hot-and-sour-soup', img: 'hot-and-sour-soup', cat: 'soup', names: ['hot and sour soup', 'veg hot and sour soup', 'hot & sour soup', 'chicken hot and sour soup'], need: ['hot', 'sour', 'soup'] },
    { id: 'manchow-soup', img: 'manchow-soup', cat: 'soup', names: ['manchow soup', 'veg manchow soup', 'chicken manchow soup'], need: ['manchow', 'soup'] },
    { id: 'lemon-coriander-soup', img: 'lemon-coriander-soup', cat: 'soup', veg: true, names: ['lemon coriander soup', 'coriander soup', 'lemon soup'], need: ['lemon', 'coriander', 'soup'] },
    { id: 'cream-of-mushroom-soup', img: 'cream-of-mushroom-soup', cat: 'soup', veg: true, names: ['cream of mushroom soup', 'mushroom soup', 'cream mushroom soup'], need: ['mushroom', 'soup'] },
    { id: 'veg-noodle-soup', img: 'veg-noodle-soup', cat: 'soup', names: ['veg noodle soup', 'noodle soup', 'talumein soup', 'chicken noodle soup'], need: ['noodle', 'soup'] },
    { id: 'veg-clear-soup', img: 'veg-clear-soup', cat: 'soup', veg: true, names: ['veg clear soup', 'clear soup', 'clear vegetable soup', 'vegetable clear soup'], need: ['clear', 'soup'] },
    { id: 'soup', img: 'soup', cat: 'soup', names: ['soup', 'shorba', 'rasam', 'chowder', 'seafood chowder', 'yakhni soup', 'tom yum', 'tom yum soup', 'egg drop soup'], need: ['soup', 'shorba', 'rasam', 'chowder'] },
    { id: 'salad', img: 'salad', cat: 'soup', veg: true, names: ['green salad', 'garden salad', 'greek salad', 'caesar salad', 'russian salad', 'kachumber salad', 'onion salad', 'fruit salad', 'sprout salad', 'salad'], need: ['salad', 'salaad', 'kachumber'] },
    { id: 'thali', img: 'thali', cat: 'main', names: ['veg thali', 'special thali', 'deluxe thali', 'mini thali', 'punjabi thali', 'gujarati thali', 'rajasthani thali', 'south indian thali', 'non veg thali', 'executive thali', 'thali', 'combo meal', 'meals', 'full meals', 'dal bati', 'dal baati', 'dal baati churma'], need: ['thali', 'meals', 'meal', 'combo', 'bati', 'baati'] },
    { id: 'raita', img: 'raita', cat: 'main', veg: true, names: ['boondi raita', 'mix veg raita', 'cucumber raita', 'pineapple raita', 'raita', 'plain curd', 'dahi', 'curd'], avoid: ['puri', 'vada', 'bhalla', 'rice', 'chicken', 'kebab'] },
    { id: 'papad', img: 'papad', cat: 'starter', veg: true, names: ['papad', 'masala papad', 'roasted papad', 'fried papad', 'papadum'] },
    { id: 'tea', img: 'tea', cat: 'beverage', veg: true, names: ['masala chai', 'adrak chai', 'ginger tea', 'masala tea', 'cutting chai', 'chai', 'tea', 'kadak chai', 'elaichi chai', 'green tea', 'lemon tea', 'black tea', 'kulhad chai', 'tandoori chai'], need: ['chai', 'tea', 'chaay', 'cha'], avoid: ['iced', 'ice'] },
    { id: 'coffee-hot', img: 'coffee-hot', cat: 'beverage', veg: true, names: ['hot coffee', 'filter coffee', 'cappuccino', 'espresso', 'latte', 'cafe latte', 'americano', 'black coffee', 'south indian filter coffee', 'coffee', 'mocha', 'flat white'], need: ['coffee', 'cofee', 'coffe', 'kaapi', 'cappuccino', 'capuccino', 'espresso', 'latte', 'americano', 'mocha'], avoid: ['cold', 'iced', 'ice', 'frappe', 'shake', 'frappuccino', 'chilled'] },
    { id: 'hot-chocolate', img: 'coffee-hot', cat: 'beverage', veg: true, names: ['hot chocolate', 'hot chocolate milk', 'cocoa', 'hot cocoa', 'drinking chocolate'] },
    { id: 'coffee-cold', img: 'coffee-cold', cat: 'beverage', veg: true, names: ['cold coffee', 'iced coffee', 'cold coffee with ice cream', 'frappe', 'coffee frappe', 'iced latte', 'cold brew', 'chilled coffee', 'frappuccino'], need: ['coffee', 'cofee', 'coffe', 'frappe', 'latte', 'brew', 'frappuccino'], keysIfNeed: ['cold', 'iced', 'ice', 'frappe', 'chilled', 'brew'] },
    { id: 'lassi', img: 'lassi', cat: 'beverage', veg: true, names: ['sweet lassi', 'salted lassi', 'mango lassi', 'lassi', 'chaas', 'chhach', 'buttermilk', 'butter milk', 'masala chaas', 'rose lassi', 'kesar lassi', 'meetha lassi'] },
    { id: 'shake', img: 'shake', cat: 'beverage', veg: true, names: ['chocolate shake', 'mango shake', 'banana shake', 'strawberry shake', 'oreo shake', 'kitkat shake', 'vanilla shake', 'milkshake', 'milk shake', 'shake', 'thick shake', 'badam milk', 'cold milk', 'rose milk', 'falooda', 'cold drink shake'], need: ['shake', 'milkshake', 'shakes', 'milk', 'falooda'], avoid: ['tea', 'coffee', 'chai', 'butter', 'paneer'] },
    { id: 'juice', img: 'juice', cat: 'beverage', veg: true, names: ['orange juice', 'fresh lime soda', 'lime soda', 'fresh lime water', 'nimbu pani', 'shikanji', 'mosambi juice', 'watermelon juice', 'pineapple juice', 'mango juice', 'apple juice', 'mixed fruit juice', 'fresh juice', 'juice', 'sugarcane juice', 'jaljeera', 'aam panna', 'virgin mojito', 'mojito', 'blue lagoon', 'mocktail', 'lemonade', 'iced tea', 'ice tea', 'cooler', 'watermelon cooler', 'pina colada', 'virgin pina colada', 'sweet lime juice', 'mosambi', 'lemon ice tea', 'peach ice tea'] },
    { id: 'soft-drink', img: 'soft-drink', cat: 'beverage', veg: true, names: ['cold drink', 'soft drink', 'coke', 'coca cola', 'pepsi', 'sprite', 'thums up', 'thumbs up', 'fanta', 'limca', 'mirinda', '7up', 'seven up', 'soda', 'aerated drink', 'masala soda', 'red bull', 'energy drink'], avoid: ['lime', 'shake', 'float'] },
    { id: 'water', img: 'water', cat: 'beverage', veg: true, names: ['mineral water', 'water bottle', 'packaged drinking water', 'bisleri', 'kinley', 'aquafina', 'water', 'drinking water'], avoid: ['melon', 'chestnut', 'pani puri'] },
    { id: 'ice-cream', img: 'ice-cream', cat: 'dessert', veg: true, names: ['vanilla ice cream', 'chocolate ice cream', 'strawberry ice cream', 'butterscotch ice cream', 'ice cream', 'icecream', 'sundae', 'hot chocolate fudge', 'kulfi', 'malai kulfi', 'kulfi falooda', 'scoop', 'gelato', 'cassata', 'brownie with ice cream'], avoid: ['coffee', 'shake'] },
    { id: 'indian-sweet', img: 'indian-sweet', cat: 'dessert', veg: true, names: ['gulab jamun', 'rasgulla', 'rasmalai', 'ras malai', 'gajar halwa', 'gajar ka halwa', 'moong dal halwa', 'kheer', 'rice kheer', 'phirni', 'jalebi', 'rabri', 'rabdi', 'jalebi rabri', 'kaju katli', 'barfi', 'ladoo', 'laddu', 'peda', 'malpua', 'sheera', 'suji halwa', 'halwa', 'shrikhand', 'payasam', 'mysore pak', 'kesari', 'imarti', 'mithai', 'shahi tukda'], avoid: ['corn', 'lassi', 'potato', 'juice', 'lime', 'soda', 'shake'] },
    { id: 'cake', img: 'cake', cat: 'dessert', veg: true, names: ['chocolate cake', 'pastry', 'black forest pastry', 'pineapple pastry', 'brownie', 'chocolate brownie', 'walnut brownie', 'muffin', 'cupcake', 'cheesecake', 'cake', 'red velvet', 'truffle cake', 'lava cake', 'choco lava cake', 'cookies', 'donut', 'doughnut'], avoid: ['ice cream', 'shake', 'icecream'] }
  ];

  // ---------- normalising ----------
  // Common Hindi (Devanagari) dish words → the Latin word used in the dictionary
  const HI = {
    'पनीर': 'paneer', 'बटर': 'butter', 'मक्खन': 'makhani', 'मसाला': 'masala', 'शाही': 'shahi', 'कढ़ाई': 'kadai', 'कड़ाही': 'kadai', 'कढाई': 'kadai', 'टिक्का': 'tikka', 'मटर': 'matar', 'पालक': 'palak',
    'वेज': 'veg', 'वेज़': 'veg', 'सब्जी': 'sabzi', 'सब्ज़ी': 'sabzi', 'मिक्स': 'mix', 'आलू': 'aloo', 'गोभी': 'gobi', 'भिंडी': 'bhindi', 'कोफ्ता': 'kofta', 'मलाई': 'malai', 'काजू': 'kaju', 'मशरूम': 'mushroom',
    'दाल': 'dal', 'मखनी': 'makhani', 'मखानी': 'makhani', 'तड़का': 'tadka', 'तडका': 'tadka', 'फ्राई': 'fry', 'राजमा': 'rajma', 'छोले': 'chole', 'चना': 'chana', 'भटूरे': 'bhature', 'भटूरा': 'bhatura', 'कढ़ी': 'kadhi', 'कढी': 'kadhi', 'सांभर': 'sambar', 'सांबर': 'sambar',
    'चिकन': 'chicken', 'मुर्ग': 'murgh', 'मटन': 'mutton', 'गोश्त': 'gosht', 'कीमा': 'keema', 'अंडा': 'anda', 'अंडे': 'anda', 'एग': 'egg', 'मछली': 'machli', 'फिश': 'fish', 'तंदूरी': 'tandoori', 'कबाब': 'kebab', 'सीख': 'seekh',
    'बिरयानी': 'biryani', 'बिरियानी': 'biryani', 'पुलाव': 'pulao', 'जीरा': 'jeera', 'चावल': 'chawal', 'राइस': 'rice', 'खिचड़ी': 'khichdi', 'खिचडी': 'khichdi', 'फ्राइड': 'fried',
    'नूडल्स': 'noodles', 'चाउमीन': 'chowmein', 'चौमीन': 'chowmein', 'मंचूरियन': 'manchurian', 'चिली': 'chilli', 'मोमोज': 'momos', 'मोमो': 'momos', 'स्प्रिंग': 'spring', 'रोल': 'roll',
    'डोसा': 'dosa', 'दोसा': 'dosa', 'इडली': 'idli', 'वड़ा': 'vada', 'वडा': 'vada', 'उत्तपम': 'uttapam', 'उपमा': 'upma',
    'नान': 'naan', 'रोटी': 'roti', 'तंदूरी रोटी': 'tandoori roti', 'चपाती': 'chapati', 'फुलका': 'phulka', 'रुमाली': 'rumali', 'पराठा': 'paratha', 'परांठा': 'paratha', 'पूरी': 'puri', 'पुरी': 'puri', 'कुलचा': 'kulcha', 'लच्छा': 'laccha', 'गार्लिक': 'garlic', 'लहसुन': 'garlic',
    'समोसा': 'samosa', 'समोसे': 'samosa', 'कचौड़ी': 'kachori', 'कचोरी': 'kachori', 'पकोड़ा': 'pakora', 'पकौड़ा': 'pakora', 'पकोड़े': 'pakora', 'पकौड़े': 'pakora', 'भजिया': 'bhajiya', 'चाट': 'chaat', 'पानी': 'pani', 'गोलगप्पे': 'golgappa', 'गोलगप्पा': 'golgappa', 'टिक्की': 'tikki', 'भेल': 'bhel',
    'पाव': 'pav', 'भाजी': 'bhaji', 'पिज़्ज़ा': 'pizza', 'पिज्जा': 'pizza', 'पिज़ा': 'pizza', 'बर्गर': 'burger', 'सैंडविच': 'sandwich', 'सेंडविच': 'sandwich', 'फ्राइज़': 'fries', 'फ्राइज': 'fries', 'पास्ता': 'pasta',
    'सूप': 'soup', 'सलाद': 'salad', 'थाली': 'thali', 'रायता': 'raita', 'दही': 'dahi', 'पापड़': 'papad', 'पापड': 'papad',
    'चाय': 'chai', 'अदरक': 'adrak', 'कॉफी': 'coffee', 'कॉफ़ी': 'coffee', 'काफी': 'coffee', 'कोल्ड': 'cold', 'ठंडी': 'cold', 'गर्म': 'hot', 'हॉट': 'hot', 'लस्सी': 'lassi', 'छाछ': 'chaas', 'शेक': 'shake', 'मिल्क': 'milk', 'दूध': 'milk', 'जूस': 'juice', 'रस': 'juice', 'नींबू': 'nimbu', 'शिकंजी': 'shikanji', 'सोडा': 'soda', 'ड्रिंक': 'drink', 'पानी की बोतल': 'water bottle',
    'आइसक्रीम': 'icecream', 'आइस': 'ice', 'क्रीम': 'cream', 'कुल्फी': 'kulfi', 'गुलाब': 'gulab', 'जामुन': 'jamun', 'रसगुल्ला': 'rasgulla', 'रसमलाई': 'rasmalai', 'हलवा': 'halwa', 'खीर': 'kheer', 'जलेबी': 'jalebi', 'रबड़ी': 'rabri', 'लड्डू': 'ladoo', 'बर्फी': 'barfi', 'केक': 'cake', 'पेस्ट्री': 'pastry', 'ब्राउनी': 'brownie',
    'स्पेशल': 'special', 'हाफ': 'half', 'फुल': 'full', 'प्लेट': 'plate', 'ग्लास': 'glass'
  };
  // Short forms seen on Indian menus
  const ABBR = { pbm: ['paneer', 'butter', 'masala'], chk: ['chicken'], chkn: ['chicken'], ckn: ['chicken'], chiken: ['chicken'], chikan: ['chicken'], murg: ['murgh'],
    mtn: ['mutton'], btr: ['butter'], bt: ['butter'], msl: ['masala'], mas: ['masala'], tand: ['tandoori'], tndr: ['tandoori'], pnr: ['paneer'], vg: ['veg'], veggie: ['veg'], vegetable: ['veg'], vegetables: ['veg'], vegitable: ['veg'],
    nv: ['nonveg'], nonveg: ['nonveg'], spl: ['special'], sp: ['special'], cof: ['coffee'], coff: ['coffee'], 'ice-cream': ['icecream'], icecrm: ['icecream'], softy: ['icecream'], fr: ['fried'],
    roti: ['roti'], rotti: ['roti'], nan: ['naan'], biriyani: ['biryani'], briyani: ['biryani'], biriani: ['biryani'], dosai: ['dosa'], dhosa: ['dosa'], cholle: ['chole'], chhole: ['chole'], panneer: ['paneer'], paner: ['paneer'], panir: ['paneer'],
    makhni: ['makhani'], makkhani: ['makhani'], tadkaa: ['tadka'], tarka: ['tadka'], parantha: ['paratha'], paratha: ['paratha'], pakoda: ['pakora'], pakode: ['pakora'], pakore: ['pakora'], chowmin: ['chowmein'], chaomin: ['chowmein'],
    shezwan: ['schezwan'], szechuan: ['schezwan'], szechwan: ['schezwan'], sezwan: ['schezwan'], schezwaan: ['schezwan'], manchuria: ['manchurian'], manchoorian: ['manchurian'], chilly: ['chilli'], chili: ['chilli'],
    sandwhich: ['sandwich'], sandwitch: ['sandwich'], burgur: ['burger'], piza: ['pizza'], pizzaa: ['pizza'], margarita: ['margherita'], frys: ['fries'], icecream: ['icecream'], milkshake: ['milkshake'], cappucino: ['cappuccino'], capuccino: ['cappuccino'], expresso: ['espresso'],
    '7up': ['7up'], gulabjamun: ['gulab', 'jamun'], golgappe: ['golgappa'], panipuri: ['pani', 'puri'], pavbhaji: ['pav', 'bhaji'], vadapav: ['vada', 'pav'], chai: ['chai'], chay: ['chai'], chaay: ['chai'], coldcoffee: ['cold', 'coffee'], frenchfries: ['french', 'fries'] };
  // Words that never decide a dish (sizes, portions, marketing)
  const NOISE = new Set(['half', 'full', 'plate', 'plates', 'pc', 'pcs', 'piece', 'pieces', 'glass', 'cup', 'bowl', 'portion', 'regular', 'large', 'small', 'medium', 'big', 'mini', 'jumbo', 'single', 'double', 'with', 'and', 'n', 'the', 'of', 'a', 'ka', 'ki', 'ke', 'e', 'style', 'house', 'chef', 'chefs', 'special', 'spl', 'new', 'fresh', 'hot', 'ml', 'ltr', 'l', 'kg', 'gm', 'g', 'qtr', 'quarter', 'nos', 'no', 'combo', 'deluxe', 'premium', 'classic', 'royal', 'desi', 'homemade', 'home', 'made', 'extra', 'add', 'on', 'addon', 'stuffed', 'dry', 'gravy']);
  // These stay meaningful in the few names that use them (hot coffee, combo meal…)
  const KEEP_IN_NAMES = new Set(['hot', 'combo', 'dry', 'gravy', 'special', 'stuffed', 'home']);
  const MEAT = new Set(['chicken', 'murgh', 'murg', 'mutton', 'gosht', 'lamb', 'keema', 'egg', 'eggs', 'anda', 'fish', 'prawn', 'prawns', 'machli', 'jhinga', 'nonveg', 'pomfret', 'surmai', 'beef', 'pork', 'bacon', 'pepperoni', 'ham', 'crab', 'seafood']);

  const MEAT_LONG = [...MEAT].filter(m => m.length >= 5);
  // Indian spellings vary in vowels and "h": compare a squashed form (paneer/panir, makhani/makhni, chicken/chiken)
  const squash = w => w.replace(/(.)\1+/g, '$1').replace(/ee|ii/g, 'i').replace(/oo|uu/g, 'u').replace(/aa/g, 'a').replace(/([bcdgjkptsr])h/g, '$1')
    .replace(/w/g, 'v').replace(/z/g, 'j').replace(/q/g, 'k').replace(/ck/g, 'k').replace(/y$/, 'i').replace(/e$/, '');

  function words(s){
    let t = String(s || '').normalize('NFC').toLowerCase();
    t = t.replace(/[़ँ]/g, '');                        // nukta, chandrabindu
    for(const [k, v] of Object.entries(HI)) if(k.includes(' ') && t.includes(k)) t = t.split(k).join(' ' + v + ' ');
    t = t.replace(/\bnon[\s-]*veg(etarian)?\b/g, ' nonveg ').replace(/\(.*?\)|\[.*?\]/g, ' ').replace(/&/g, ' and ').replace(/[^0-9a-zऀ-ॿ]+/g, ' ');
    const out = [];
    for(let w of t.split(' ').filter(Boolean)){
      if(/[ऀ-ॿ]/.test(w)) w = HI[w] || hiFuzzy(w) || w;
      if(/^\d+$/.test(w) && w !== '65' && w !== '7') continue;     // "2 pcs", "250", but "chicken 65", "7up" stay
      for(const x of String(w).split(' ')){
        const e = ABBR[x];
        if(e) out.push(...e); else out.push(x);
      }
    }
    return out;
  }
  const HI_KEYS = Object.keys(HI).filter(k => !k.includes(' '));
  function hiFuzzy(w){
    let best = null, bd = 9;
    for(const k of HI_KEYS){
      if(Math.abs(k.length - w.length) > 1) continue;
      const d = dist(k, w, 2);
      if(d < bd){ bd = d; best = k; }
    }
    return best && bd <= (w.length >= 5 ? 1 : 0) ? HI[best] : null;
  }

  // Damerau-Levenshtein with an early stop
  function dist(a, b, max){
    if(a === b) return 0;
    if(Math.abs(a.length - b.length) > max) return max + 1;
    const m = a.length, n = b.length, d = [];
    for(let i = 0; i <= m; i++){ d[i] = [i]; }
    for(let j = 0; j <= n; j++) d[0][j] = j;
    for(let i = 1; i <= m; i++){
      let low = 99;
      for(let j = 1; j <= n; j++){
        const c = a[i - 1] === b[j - 1] ? 0 : 1;
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c);
        if(i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
        if(d[i][j] < low) low = d[i][j];
      }
      if(low > max) return max + 1;
    }
    return d[m][n];
  }
  // Two words are "the same" when equal, or squashed-equal, or one typo apart (long words only)
  const memo = new Map();
  function same(a, b){
    if(a === b) return 1;
    const k = a + '|' + b;
    let v = memo.get(k);
    if(v === undefined){ v = same0(a, b); if(memo.size > 200000) memo.clear(); memo.set(k, v); }
    return v;
  }
  const SQ = new Map();
  const sq = w => { let v = SQ.get(w); if(v === undefined){ v = squash(w); if(SQ.size > 50000) SQ.clear(); SQ.set(w, v); } return v; };
  function same0(a, b){
    const sa = sq(a), sb = sq(b);
    if(sa === sb && sa.length >= 3) return 0.97;
    const L = Math.min(a.length, b.length);
    if(L < 6 || sa[0] !== sb[0] || Math.abs(sa.length - sb.length) > 2) return 0;
    if(dist(sa, sb, 1) <= 1) return 0.9;
    if(L >= 8 && dist(sa, sb, 2) <= 2) return 0.85;
    return 0;
  }
  const hasWord = (ws, w) => ws.reduce((best, x) => Math.max(best, same(x, w)), 0);

  // ---------- index ----------
  const prepared = DISH.map(e => ({
    ...e,
    alias: e.names.map(n => words(n).filter(w => !NOISE.has(w) || KEEP_IN_NAMES.has(w))).filter(a => a.length),
    need: e.need || null, avoid: (e.avoid || []).map(a => a.split(' ')), keysIfNeed: e.keysIfNeed || null
  }));
  const byId = Object.fromEntries(prepared.map(e => [e.id, e]));
  // Word → dishes that use it, so a name is only compared with dishes sharing a word
  const INDEX = new Map();
  prepared.forEach(e => {
    const vocab = new Set([...e.alias.flat(), ...(e.need || []), ...(e.keysIfNeed || [])]);
    vocab.forEach(w => { if(!INDEX.has(w)) INDEX.set(w, new Set()); INDEX.get(w).add(e); });
  });
  // Grouped by the first letter of the squashed word: a match always shares it
  const VOCAB = new Map();
  for(const v of INDEX.keys()){ const c = sq(v)[0] || ''; if(!VOCAB.has(c)) VOCAB.set(c, []); VOCAB.get(c).push(v); }
  const candidates = ws => {
    const out = new Set();
    for(const w of ws) for(const v of VOCAB.get(sq(w)[0] || '') || []) if(same(w, v)) INDEX.get(v).forEach(e => out.add(e));
    return out;
  };

  const avoided = (entry, ws, alias) => entry.avoid.some(av => av.every(w => hasWord(ws, w) >= 0.97 && !(alias && alias.includes(w))));

  function score(entry, ws, meat, ccat){
    // Hard rules first: a wrong picture is worse than no picture
    if(entry.meat && !meat) return 0;                            // veg name never gets a non-veg picture
    if(entry.needMeat && !meat) return 0;
    if(!entry.meat && entry.veg && meat && !entry.needMeat) return 0;   // chicken biryani never gets the veg biryani picture
    if(entry.need && !entry.need.some(w => hasWord(ws, w) >= 0.9)) return 0;
    let best = 0;
    for(const a of entry.alias){
      let tot = 0, ok = true;
      for(const w of a){ const s = hasWord(ws, w); if(!s){ ok = false; break; } tot += s; }
      if(!ok) continue;
      // A word to avoid stops the match, unless the dish's own name has it ("paneer tikka masala")
      if(avoided(entry, ws, a)) continue;
      const fit = tot / a.length;                                // 1 = every word exact
      const extra = Math.max(0, ws.length - a.length);           // name words the alias does not explain
      let sc = (a.length === ws.length ? 1 : 0.93 - Math.min(0.12, extra * 0.04)) * fit;
      if(a.length === 1 && ws.length > 1) sc -= 0.03;            // one-word alias inside a longer name: a bit less sure
      best = Math.max(best, sc);
    }
    if(best || avoided(entry, ws, null)) return best;
    // "paneer" + a curry word, "coffee" + cold… : the family by its key words
    if(entry.need && entry.keysIfNeed && entry.keysIfNeed.some(k => hasWord(ws, k) >= 0.9)) return 0.82;
    // The menu's category as the second clue: "Chicken Hyderabadi" under "Chicken Main Course" is a chicken curry
    if(entry.assist && ccat === 'main'){
      if(entry.need) return 0.8;
      if(entry.assistKeys && entry.assistKeys.some(k => hasWord(ws, k) >= 0.9)) return 0.8;
    }
    return 0;
  }

  function catOf(category, ws){
    const cw = words(category).map(w => w.replace(/s$/, ''));
    const joined = cw.join('');
    for(const [c, list] of Object.entries(CAT_WORDS)) if(list.some(x => cw.includes(x.replace(/s$/, '')) || joined === x)) return c;
    for(const [c, list] of Object.entries(CAT_WORDS)) if(list.some(x => ws.includes(x))) return c;
    return 'generic';
  }

  const cache = new Map();
  // foodType (optional): the menu's own Veg / Non-Veg column. It is a hard rule both ways.
  const typeOf = t => { t = String(t || '').toLowerCase().replace(/[^a-z]/g, ''); return !t ? null : /^(nonveg|nv|egg|eggetarian|meat|nonvegetarian)$/.test(t) ? 'nonveg' : /^(veg|vegetarian|v|jain|vegan)$/.test(t) ? 'veg' : null; };
  function match(name, category, foodType){
    const key = name + '\u0001' + (category || '') + '\u0001' + (foodType || '');
    if(cache.has(key)) return cache.get(key);
    const all = words(name);
    const ws = all.filter(w => !NOISE.has(w) || KEEP_IN_NAMES.has(w));
    const named = ws.some(w => MEAT.has(w) || MEAT_LONG.some(m => same(w, m) >= 0.9));
    const ft = typeOf(foodType);
    const meat = ft ? ft === 'nonveg' : named;
    const ccat = catOf(category, []);
    let best = null, second = null;
    if(ws.length) for(const e of candidates(ws)){
      const s = score(e, ws, meat, ccat);
      if(s <= 0) continue;
      if(!best || s > best.s){ second = best; best = {e, s}; } else if(!second || s > second.s) second = {e, s};
    }
    const cat = catOf(category, ws);
    let res;
    if(best){
      let conf = best.s;
      // Two different pictures nearly tied: let the owner decide
      if(second && second.e.img !== best.e.img && best.s - second.s < 0.05) conf = Math.min(conf, 0.7);
      // The name says chicken but the Food Type column says Veg (or the other way): the owner decides
      if(ft && named !== meat) conf = Math.min(conf, 0.6);
      if(category && ccat !== 'generic'){
        if(ccat === best.e.cat || (ccat === 'main' && ['main', 'rice', 'bread'].includes(best.e.cat)) || (ccat === 'starter' && ['starter', 'snacks', 'chinese'].includes(best.e.cat))) conf = Math.min(1, conf + 0.03);
        else if(['beverage', 'dessert'].includes(ccat) !== ['beverage', 'dessert'].includes(best.e.cat)) conf -= 0.25;
      }
      conf = Math.round(Math.max(0, conf) * 100) / 100;
      res = conf >= 0.55
        ? {img: best.e.img, dish: best.e.id, conf, status: conf >= 0.8 ? 'matched' : 'review', kind: 'dish', cat: best.e.cat, placeholder: 'cat-' + best.e.cat}
        : null;
    }
    if(!res) res = {img: 'cat-' + cat, dish: '', conf: 0, status: 'placeholder', kind: cat === 'generic' ? 'generic' : 'category', cat, placeholder: 'cat-' + cat};
    if(cache.size > 20000) cache.clear();
    cache.set(key, res);
    return res;
  }

  // The picture to show for a menu item, in priority order:
  // 1. the restaurant's own upload (m.photo) · 2. its own https link (m.img) · 3. a library picture the owner chose (m.lib)
  // 4. an automatic match the owner confirmed or that is confident · 5. the category placeholder
  function pick(m){
    if(!m) return {src: 'cat-generic', kind: 'generic'};
    if(/^m_[0-9a-f]{32}$/.test(m.photo || '')) return {src: m.photo, kind: 'custom'};
    if(m.img && (/^(https?:\/\/|[a-zA-Z0-9_\-\.\/]+$)/.test(m.img) && !m.img.includes('..'))) return {src: m.img, kind: 'link'};
    if(m.lib && LIB.has(m.lib)) return {src: m.lib, kind: 'chosen'};
    if(m.lib && byId[m.lib]) return {src: byId[m.lib].img, kind: 'chosen'};
    if(m.lib === 'none') return {src: 'cat-' + catOf(m.cat, words(m.name)), kind: 'category'};
    const r = match(m.name, m.cat, m.veg === true ? 'veg' : m.veg === false ? 'nonveg' : '');
    return r.status === 'matched' ? {src: r.img, kind: 'auto', conf: r.conf} : {src: r.placeholder, kind: r.status === 'review' ? 'review' : r.kind, conf: r.conf, suggest: r.status === 'review' ? r.img : ''};
  }

  const images = () => [...new Set(prepared.map(e => e.img))];
  // Every picture file in the library (dish pictures + category placeholders): nothing else may become a file name
  const LIB = new Set([...images(), ...Object.keys(CATS).map(c => 'cat-' + c)]);
  const dishes = () => prepared.map(e => ({id: e.id, img: e.img, cat: e.cat, label: e.names[0]}));
  const api = {match, pick, words, dishes, images, CATS, isPicture: id => LIB.has(id), version: 1};
  root.FoodVisuals = api;
  if(typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
