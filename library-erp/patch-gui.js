// Exe ko Windows GUI app bana deta hai — kholne par kaali console window nahi dikhegi.
const fs = require('fs');
const f = process.argv[2];
const b = fs.readFileSync(f);
const pe = b.readUInt32LE(0x3c);
if (b.toString('latin1', pe, pe + 4) !== 'PE\0\0') throw new Error('PE header nahi mila: ' + f);
b.writeUInt16LE(2, pe + 0x5c); // IMAGE_SUBSYSTEM_WINDOWS_GUI
fs.writeFileSync(f, b);
console.log('GUI exe: ' + f);
