const fs = require('fs');
const html = fs.readFileSync('hotel-erp/hotel_erp.html', 'utf8');

const idx = html.indexOf('function scrGateway');
console.log(html.substring(idx + 500, idx + 3500));
