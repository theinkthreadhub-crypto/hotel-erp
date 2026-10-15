from common import *
B = []
a = B.append
a('<h1 class="first">Is guide me kya hai</h1>')
a('<p class="lead">Ye guide aapko <b>Library ERP</b> chalana step-by-step sikhati hai — pehli baar install karne se lekar roz ka fee collection, attendance, students ka app, backup aur renewal tak. Har kaam ke saath asli screen ki photo di gayi hai.</p>')
a('<div class="card3"><div><b>🖥️ Library ERP</b>Aapka main software. Windows computer (exe) ya Android phone (APK) par chalta hai. Internet ke bina bhi chalta hai.</div><div><b>📱 Student App</b>Har student ka apna link / app. Khud IN-OUT lagaye, fee aur attendance dekhe, aapke message padhe.</div><div><b>🌐 Online View</b>Aap kahin se bhi phone par aaj ki collection, due aur attendance dekh sakte hain.</div></div>')
a('<h2>Chapters</h2><table class="toc">' + ''.join(f'<tr><td class="n">{n}</td><td>{t}</td></tr>' for n, t in [
 (1,'Install karna (Windows / Android)'),(2,'Activation — software chalu karna'),(3,'Pehli baar setup (15 minute)'),(4,'Gateway aur keyboard shortcuts'),(5,'New Admission — naya student'),
 (6,'Fee Collect — receipt banana'),(7,'Attendance — IN / OUT'),(8,'Due List aur Fee Reminder (WhatsApp)'),(9,'Student List aur Student Record'),(10,'Kharcha, Day Book aur Reports'),
 (11,'Student App — students ko link dena'),(12,'Students ko message bhejna'),(13,'Backup aur data ki suraksha'),(14,'Online View — phone par hisaab'),(15,'License renew aur Setu Pro ke message'),
 (16,'Help & Support'),(17,'Aksar aane wali dikkatein'),(18,'Roz ka routine aur Do / Don\'t')]) + '</table>')
a(box('info','Pehle ye yaad rakhein','<ul><li>Software <b>English</b> me hai, taaki receipt aur reports professional dikhein.</li><li>Poora kaam <b>keyboard</b> se ho sakta hai, phone par <b>touch</b> se.</li><li>Aapka data aapke computer / phone me rehta hai. Internet milte hi cloud par apne aap <b>backup</b> ho jata hai.</li><li>Kuch bhi atke to <b>6392995127</b> (Setu Pro) par call / WhatsApp karein.</li></ul>'))

a('<h1>1. Install karna</h1><h2>Windows computer (exe)</h2>')
a(steps('Setu Pro se mili file <code>LibraryERP-Setup-vX.X.X.exe</code> computer me copy karein (pen drive / WhatsApp se).','File par <b>double click</b> karein → <b>Next → Install</b>. Desktop par <b>Library ERP</b> icon aa jayega.','Windows ek chetavni dikha sakta hai ("Windows protected your PC"). <b>More info → Run anyway</b> dabayein. Ye normal hai, software safe hai.','Desktop icon se <b>Library ERP</b> kholein. Ek kaali (ya chhoti) window khulti hai — use <b>band na karein</b>, sirf minimize karein. Saath me ERP browser window me khulta hai.'))
a(box('warn','Window band mat karna','Library ERP chalte rehne ke liye wo chhoti window khuli rehni chahiye. Band karne par ERP band ho jata hai (data safe rehta hai, bas dobara icon se kholein).'))
a('<h2>Android phone (APK)</h2>')
a(steps('Setu Pro se mili <code>LibraryERP-vX.X.X.apk</code> file phone me save karein.','File par tap karein. Phone puchhe to <b>"Install unknown apps"</b> ko <b>Allow</b> karein (sirf is baar ke liye).','<b>Install → Open</b>. Phone ke home screen par <b>Library ERP</b> icon aa jayega.'))
a(box('tip','Naya version aaye to','Naya exe / APK usi tarah install karein — <b>purana data apne aap wahi rehta hai</b>. Pehle se uninstall karne ki zarurat nahi.'))

a('<h1>2. Activation — software chalu karna</h1><p>Pehli baar ERP kholte hi ye screen aati hai. Software ek hi computer / phone ke liye activate hota hai, isliye <b>Machine code</b> chahiye.</p>')
a(fig('d_activate','Activation screen: Machine code, Setu Pro ka number, aur key paste karne ka box.',900))
a(steps('Screen par dikhne wala <b>Machine code</b> (jaise <code>3D1EA-73DCE</code>) dekhein.','<b>Send on WhatsApp</b> dabayein ya <b>Code copy</b> karke Setu Pro (6392995127) ko bhejein.','Setu Pro aapko ek lambi <b>Activation Key</b> bhejega (<code>LIB-…</code> se shuru).','Key ko poora <b>copy</b> karke "Paste the activation key here" box me <b>paste</b> karein → <b>Activate (Ctrl+Enter)</b>.','Setu Pro agar key cloud se bhej de to bas <b>Check cloud renewal</b> dabayein (internet on rakhein) — ERP khud activate ho jayega.'))
a(row(['m_activate','m_home'],['Phone par bhi wahi tareeka: Machine code → key → Activate','Activate hone ke baad phone ka Home screen'],420))
a(box('warn','Machine code badalta hai kab?','Windows dobara install karne ya naya computer lene par Machine code badal jata hai. Tab Setu Pro se <b>nayi key</b> maangni padegi. Purana data cloud se wapas laya ja sakta hai (chapter 13).'))

a('<h1>3. Pehli baar setup (15 minute)</h1><p>Ye kaam sirf ek baar karna hai. Pehle <span class="k">G</span> (Settings) se shuru karein.</p>')
a('<h2>Step A — Library ki details (Settings & Backup)</h2>')
a(fig('d_settings','Settings: library ka naam, address, contact, logo, receipt ka size aur WhatsApp ka tareeka.',1000))
a(steps('Gateway par <span class="k">U</span> dabayein → <b>Settings & Backup</b> (ya <span class="k">Alt+G</span>).','<b>Library name</b>, <b>Address</b>, <b>Contact number</b> bharein. Ye receipt par chhapta hai.','<b>Upload logo</b> se apni library ka logo lagayein (PNG / JPG). Logo receipt par aur students ke app me dikhta hai. <b>Student app ke icon ke liye logo zaroori hai.</b>','<b>Slip size</b> chunein (58 mm / 80 mm thermal, ya A4 / A5 / A6) aur <b>Test print</b> karke dekh lein.','<b>After saving a receipt</b> me chunein: har baar poochho / seedha WhatsApp / seedha Print / dono.','<b>Save Settings (Ctrl+S)</b> dabayein.'))
a('<h2>Step B — Fee Master (fee ke plan)</h2>')
a(fig('d_plans','Fee Master: Full day ₹600, Half day ₹400 (30 din = mahine ki fee) aur Admission fee ₹200 (0 din = ek baar ki fee).',1000))
a(steps('<span class="k">M</span> → <b>Fee Master</b> (<span class="k">Alt+F</span>).','Fee ka <b>naam</b>, <b>amount</b> aur <b>validity (din)</b> likhein. <code>30</code> = mahine wali fee. <code>0</code> = sirf ek baar wali (Admission, Security).','<b>Order No.</b> se tay karein kaun upar dikhe (1 sabse upar).','Kai fee ek saath banani ho to "Ek saath kai fee" box me har line par <code>Naam, Amount, Din, Order</code> likhein.'))
a('<h2>Step C — Session aur kharche ke heads</h2>')
a(ul('<b>Sessions (<span class="k">Alt+N</span>)</b>: saal ka session (jaise 2026-27 = 01-04-2026 se 31-03-2027). Upar patti me <b>Session</b> dropdown se session badal sakte hain. Har receipt us session ki hoti hai.','<b>Expense Heads (<span class="k">Alt+H</span>)</b>: Rent, Electricity, WiFi, Salary jaise naam pehle se bane hote hain. Zarurat ho to naye jod lein.'))
a(box('tip','Purane students hain?','Excel / CSV se ek saath daal sakte hain: <b>Utilities → Bulk Import (<span class="k">I</span>)</b>. Setu Pro ka Excel format download karke bharein. Ya har student me <b>"Fee paid till"</b> date likhein, taaki purani fee dobara due na dikhe.'))

a('<h1>4. Gateway aur keyboard shortcuts</h1><p>ERP kholte hi <b>Gateway</b> aata hai — upar dashboard me aaj ki collection, kitni fee baaki, kharcha, profit / loss aur aaj kitne students aaye, sab ek nazar me.</p>')
a(fig('d_home','Gateway: 4 menu (Masters, Transactions, Reports, Utilities) aur upar ka hisaab.',1000))
a(table(['Menu','Letter','Kaam'],[
 ['<b>M</b> Masters','<span class="k">S</span> New Admission · <span class="k">L</span> Student List · <span class="k">F</span> Fee Master · <span class="k">H</span> Expense Heads · <span class="k">O</span> Books · <span class="k">N</span> Sessions','Ek baar banane wali cheezein'],
 ['<b>T</b> Transactions','<span class="k">C</span> Fee Collect · <span class="k">E</span> Expense · <span class="k">A</span> Attendance · <span class="k">J</span> Book Issue/Return · <span class="k">Z</span> Fee Reminder','Roz ka kaam'],
 ['<b>R</b> Reports','<span class="k">B</span> Day Book · <span class="k">P</span> Receipt List · <span class="k">D</span> Due List · <span class="k">V</span> Income vs Expense · <span class="k">X</span> Expense Report · <span class="k">W</span> Attendance Report · <span class="k">Y</span> Book Register','Hisaab dekhna'],
 ['<b>U</b> Utilities','<span class="k">I</span> Bulk Import · <span class="k">G</span> Settings & Backup · <span class="k">K</span> License · <span class="k">Q</span> Close','Settings aur license']]))
a(ul('<span class="k">M</span> / <span class="k">T</span> / <span class="k">R</span> / <span class="k">U</span> dabane par us menu ki list khulti hai. <span class="k">↑</span> <span class="k">↓</span> + <span class="k">Enter</span> se chunein.','Kisi bhi screen se <span class="k">Alt</span> + letter dabakar seedha jaa sakte hain (jaise <span class="k">Alt+C</span> = Fee Collect).','<span class="k">Esc</span> = wapas Gateway. <span class="k">Ctrl+S</span> = Save.','Student Record me: <span class="k">F2</span> Edit · <span class="k">F4</span> Fee collect · <span class="k">F9</span> WhatsApp.'))
a(fig('d_menu_t','Transactions menu khula hua (T dabane par).',900))
a(box('info','Phone par','Phone par keyboard ki jagah neeche ka <b>menu bar</b> aur <b>☰ Menu</b> hai: Home, Fee, Attendance, Students, Menu. Home par bade tiles hain (New Admission, Fee Collect, Attendance, Due List…).'))
a(row(['m_home','m_drawer'],['Phone ka Home — bade tiles','☰ Menu — saare modules'],420))

a('<h1>5. New Admission — naya student</h1>')
a(fig('d_admission','New Admission: left me student ki details, right me fee ki jaankari.',1000))
a(steps('<span class="k">Alt+S</span> dabayein (ya Gateway → Masters → New Admission).','<b>Student ID</b> apne aap aa jati hai (badal bhi sakte hain). <b>Student name</b>, <b>Mobile (WhatsApp)</b> aur <b>Fee Plan</b> zaroori hain (laal * wale).','Father ka naam, Address, Aadhaar number (optional), Seat, Shift bhi bhar sakte hain.','<b>Admission / Join date</b> sahi rakhein — isi se pata chalta hai kis mahine se fee banti hai.','<span class="k">Ctrl+S</span> / <b>Save</b>. Save karte hi aap turant fee le sakte hain.'))
a(box('tip','Student ka link apne aap banta hai','Admission ke saath student ka app-link bhi ban jata hai (chapter 11). Pehli receipt ke WhatsApp ke saath wo link student ko chala jata hai.'))
a(box('warn','Galti se student ban gaya?','Student Record kholein → <b>Delete</b> dabayein. Dhyan: student ki saari fee receipts bhi hat jati hain. Pehle sochein, confirm box aayega.'))

a('<h1>6. Fee Collect — receipt banana</h1>')
a(fig('d_collect','Fee Collect: mahine tick karein (hare = paid, laal = due), amount likhein, Save Receipt.',1000))
a(steps('<span class="k">Alt+C</span> dabayein. <b>Select student</b> box me naam / ID / mobile / seat likhein → <span class="k">Enter</span>.','Right side me student ki fee ki sthiti dikhti hai: kitne mahine due, purana balance.','<b>Months</b> tick karein (Space dabakar ya mouse se). Paid mahine hare dikhte hain aur dubara nahi chunne dete. Aage ke mahine bhi (Advance) le sakte hain.','Ek baar wali fee (jaise Admission fee) ho to "One-time fees" me tick karein.','Zarurat ho to <b>Discount</b> likhein.','<b>Received (₹)</b> me jitna paisa mila wahi likhein. <b>Mode</b> chunein: Cash / UPI / Card / Bank. UPI ho to Note me reference likh dein.','<b>Save Receipt</b> dabayein.'))
a(fig('d_receipt_ask','Receipt save hone ke baad: Print, WhatsApp, ya dono.',900))
a(ul('<b>Print (P)</b> — receipt printer se. <b>WhatsApp (W)</b> — seedha student ki chat me receipt ka message khulta hai, bas <b>Send</b> dabana hai. <b>Print + WhatsApp (B)</b> — dono.','<b>Next student (N)</b> — agle student ki fee. <b>Done (H)</b> — Gateway.','Agar student ka WhatsApp number alag hai (jaise father ka) to Fee Collect me <b>WhatsApp no. (optional)</b> me wo number likhein.'))
a('<h2>Adhuri fee (partial payment) kaise hoti hai</h2>')
a(table(['Maan lijiye','Aap likhenge','Kya hoga'],[
 ['Mahine ki fee ₹500, student ne ₹250 diye','Month tick, <b>Received = 250</b>','Receipt me ₹250 jama, <b>₹250 Balance</b> student par baaki'],
 ['Agle mahine student aaya','Naya month tick karein','Total = naya mahina ₹500 + purana balance ₹250 = <b>₹750</b>. Pehle purana balance kat jata hai, phir naye mahine ki fee'],
 ['Kuch discount dena ho','Discount me amount','Total me se ghat jata hai']]))
a(box('danger','Galat receipt bani?','<span class="k">P</span> (Receipt List) → us receipt par <b>Delete</b>. Student ki sthiti pehle jaisi ho jati hai. Dhyan se karein — hamesha confirm box aata hai.'))

a('<h1>7. Attendance — IN / OUT</h1>')
a(fig('d_att','Attendance: ID likhkar Enter — pehli baar IN, doosri baar OUT. Table me IN, OUT, kitni der ruka.',1000))
a(steps('<span class="k">Alt+A</span> dabayein. Upar ka <b>Date</b> aaj ka hota hai.','<b>Student ID / Seat / Mobile</b> likhkar <span class="k">Enter</span> dabayein → pehli baar <b>IN</b> ka time lagta hai.','Student jate waqt phir wahi ID + Enter → <b>OUT</b> ka time lagta hai aur kitni der ruka wo dikhta hai.','Table me <b>Present / Inside now / Absent</b> ginti dikhti hai. Ghadi ka time galat ho to time par click karke badal sakte hain.','Fee due wale student ke naam ke saath laal <b>Fee due</b> tag aata hai — aap use yaad dila sakte hain.'))
a(box('tip','Students khud bhi laga sakte hain','Student app me <b>Mark IN / Mark OUT</b> dabane par attendance apne aap ERP me aa jati hai (chapter 11). ERP me ye lagbhag <b>3 minute</b> me dikhti hai (computer / phone internet par ho).'))
a(ul('<b>Month Report (M)</b>: poore mahine ka P/A grid aur % — print aur CSV bhi.'))

a('<h1>8. Due List aur Fee Reminder (WhatsApp)</h1>')
a(fig('d_due','Due List: kis student ki kitni fee baaki hai.',1000))
a(steps('<span class="k">D</span> (Reports) → <b>Due List</b>. Upar se filter: sab / due / jaldi khatam hone wale / balance wale.','<span class="k">Alt+Z</span> → <b>Fee Reminder</b> me ek-ek karke student ko WhatsApp reminder bhejein. "Sent today ✓" dikhta hai taaki dobara na jaye.','<b>Message templates</b> khud badal sakte hain. <code>{name}</code>, <code>{month}</code>, <code>{amount}</code>, <code>{last_date}</code> jaise shabd apne aap bhar jate hain.'))
a(fig('d_remind','Fee Reminder: ek-ek student ko WhatsApp reminder.',1000))
a(box('info','Gateway par popup','Roz pehli baar ERP kholne par due fee ka ek <b>popup</b> bhi aata hai, taaki aap bhool na jayein.'))

a('<h1>9. Student List aur Student Record</h1>')
a(fig('d_list','Student List: naam / ID / mobile se dhoondhein. Kisi par Enter dabakar poora record kholein.',1000))
a(fig('d_record','Student Record: poori jaankari, har receipt, mahine ka hara/laal chart aur attendance.',1000))
a(ul('Student Record me upar ke button: <b>Collect fee (F4)</b>, <b>Edit (F2)</b>, <b>WhatsApp (F9)</b>, <b>🔗 Share link</b>, <b>📢 Message</b>.','<b>Left</b> (chhod chuke) student ko Edit me "Left" mark karein — wo list se hat jata hai par record safe rehta hai.','Galat daala hua student / receipt <b>Delete</b> kar sakte hain (confirm ke baad).'))

a('<h1>10. Kharcha, Day Book aur Reports</h1>')
a(fig('d_expense','Expense Entry: Date, Head, Amount, Mode, kisko diya.',900))
a(steps('<span class="k">Alt+E</span> → date, <b>Head</b> (Rent / Electricity…), <b>Amount</b>, <b>Mode</b>, <b>Paid to</b> → Save. Pichhle mahine ka kharcha "Use" se dobara bhar sakte hain.'))
a(row(['d_daybook','d_pl'],['Day Book: din ki fee + kharcha + cash in hand','Income vs Expense: mahine-wise profit / loss'],520))
a(table(['Report','Kya batata hai'],[['Day Book (<span class="k">B</span>)','Din bhar ki fee, kharcha, profit / loss aur <b>Cash in hand</b>'],['Receipt List (<span class="k">P</span>)','Saari receipts, dobara print, galat receipt delete'],['Income vs Expense (<span class="k">V</span>)','Mahine-wise kamai vs kharcha (profit / loss)'],['Expense Report (<span class="k">X</span>)','Head-wise kharcha'],['Attendance Report (<span class="k">W</span>)','Mahine ka P/A grid'],['Dashboard (Gateway)','Is mahine collection, baaki, outstanding, 6 mahine ka chart, poore session ka hisaab']]))
a(box('info','Books (sirf Pro plan me)','<b>Books (O)</b> me book add karein ya Excel se bulk upload. <b>Book Issue / Return (<span class="k">J</span>)</b> me student + book chun kar issue; return par late fine apne aap lagta hai. <b>Book Register (Y)</b> me bahar gayi / late books ki list.'))

a('<h1>11. Student App — students ko link dena</h1><p>Har student ka apna <b>private link</b> hota hai. Link kholne par student apna hi data dekhta hai — kisi aur ka nahi. Alag app store se kuch download nahi karna padta.</p>')
a(box('warn','Plan me hona chahiye','Student App aapke plan me ON hona chahiye. Na ho to Setu Pro (6392995127) se plan upgrade karwayein. Cloud (internet) bhi zaroori hai.'))
a('<h2>Link kaise bhejein</h2>')
a(fig('d_sharelink','Student Record → 🔗 Share link: link copy karein ya seedha WhatsApp se bhejein.',1000))
a(steps('<b>Student Record</b> kholein → <b>🔗 Share link</b>.','<b>WhatsApp to parent</b> dabayein (message aur link ke saath) ya <b>Copy link</b>.','Student link kholega → <b>Install</b> ya <b>Add to Home Screen</b> kar lega. Ab uske phone me aapki library ke naam aur logo wala icon aa jayega.'))
a(table(['Phone','Install ka tareeka'],[['Android (Chrome)','Link kholein → upar <b>Install</b> wala box ya ⋮ menu → <b>Install app / Add to Home screen</b>'],['iPhone (Safari)','Link Safari me kholein → <b>Share (⬆️)</b> → <b>Add to Home Screen</b>'],['Android — alag app (SetuStudent.apk)','Setu Pro se app lein → link <b>paste</b> karein, phir har baar seedha apna page khulta hai']]))
a('<h2>Student ko kya dikhta hai</h2>')
a(row(['st_s7_top','st_s10_fee'],['Upar: aapka (library ka) naam, message, aaj ki attendance aur <b>Mark IN / OUT</b>','Fee record: har mahine kitna diya, Cash/UPI, baaki, agla payment'],420))
a(ul('<b>Mark IN / Mark OUT</b>: time <b>server se</b> lagta hai (student badal nahi sakta). Din me ek IN aur ek OUT. OUT se pehle IN zaroori.','<b>Fee card</b>: Due kitna hai aur agla payment. <b>Fee record</b>: mahine-wise paid, "Partial / Baaki" aur payment mode.','<b>Attendance</b>: poore saal ka record — mahine chips, din-din Present / Absent, ghante.','<b>Messages</b>: aapka personal aur common message upar dikhta hai.'))
a('<h2>Consistency Challenge — students ko motivate karne wala calendar</h2>')
a(fig('st_s7_challenge','Mahine ka calendar: jis din aaya us din pen jaisa ❌, jis din nahi aaya khali circle. Do streak: is mahine ki aur poore saal ki. Roz naya quote.',520))
a(ul('<b>🔥 Is mahine</b> aur <b>🏆 Poore saal</b> ki streak (lagatar kitne din aaya) — Current aur Best.','7 / 15 / 30 din (mahina) aur 30 / 100 / 200 din (saal) par badge.','‹ › se pichhle mahine dekhein; kisi circle par tap karke us din ka IN-OUT time.','Aaj IN na lagaya ho to streak tootti nahi — din khatam hone par hi tootti hai.'))
a('<h2>Student ne app delete kar diya / naya phone liya?</h2>')
a(box('tip','Data kuch delete nahi hota','Data app me nahi, aapke ERP aur cloud me hota hai. Wahi link dobara kholne par <b>fee record, poori attendance aur streak</b> sab waisa hi milta hai. Link na mile to Student Record → <b>Share link</b> se wahi link dobara bhejein.'))
a('<h2>Link kisi aur ke paas chala gaya?</h2>')
a(steps('Student Record → <b>🔗 Share link</b> → <b>♻ New link</b>.','Naya link ban jata hai aur <b>purana link turant band</b> ho jata hai. Naya link student ko bhejein.'))

a('<h1>12. Students ko message bhejna</h1><p>Aap apne students ko ERP se message bhej sakte hain — wo seedha unke app me dikhta hai (internet aate hi ~10 second me).</p>')
a(fig('d_stumsg','Student Messages: upar Common (sabhi ke liye), neeche Personal (ek student ke liye).',1000))
a(table(['Message','Kaise bhejein','Kaun dekhega'],[['📢 <b>Common</b>','Utilities / Transactions me <b>Student Messages (App)</b> → likhein → <b>Save & show</b>','Sabhi students (neela card, "Library ki taraf se")'],['💌 <b>Personal</b>','Student Record → <b>📢 Message</b> (ya Student Messages screen me naam chunein)','Sirf us ek student ko (gulabi card, "Aapke liye message")']]))
a(ul('Message 400 akshar tak. <b>Remove</b> dabate hi app se hat jata hai.','Jaise: "Kal library band rahegi", "Aapki fee baaki hai, kal tak jama karein".','Personal message tabhi dikhega jab us student ka link ban chuka ho.'))

a('<h1>13. Backup aur data ki suraksha</h1><p>Aapka data kai jagah safe rehta hai. Phir bhi in baton ka dhyan rakhein.</p>')
a(table(['Backup','Kab / Kahan','Kya karna hai'],[
 ['<b>Roz ka local backup</b>','Computer / phone me, pichhle <b>60 din</b>','Kuch nahi — apne aap'],
 ['<b>Cloud backup</b>','Internet milte hi, <b>30 din</b> ka','Ek baar <b>PIN</b> set karein (neeche)'],
 ['<b>Email backup</b>','Roz Gmail par (optional)','Settings me Gmail + App Password'],
 ['<b>Google Drive / pen drive folder</b>','Roz us folder me copy','Settings me folder ka path'],
 ['<b>Backup download (.json)</b>','Kabhi bhi haath se','Settings → Data backup / restore']]))
a(fig('d_settings2','Settings ke neeche: Set PIN, Sync now, Restore from cloud, backup folder aur Backup by date.',1000))
a('<h2>Cloud PIN set karna (zaroori)</h2>')
a(steps('<b>Settings & Backup</b> me Setu Pro Cloud wale hisse tak jayein.','<b>4 se 6 ank ka PIN</b> likhkar <b>Set PIN</b> dabayein. Is PIN aur <b>Library ID</b> ko kisi surakshit jagah likh lein.','Upar ka <b>● Synced</b> hara ho to cloud par data pahunch gaya. <b>● Saved offline</b> ka matlab internet nahi hai — data computer me safe hai, net aate hi chala jayega.'))
a('<h2>Naya computer / phone ya data kho gaya to</h2>')
a(steps('Naya ERP install + activate karein (Setu Pro se nayi key).','<b>Settings → Restore from cloud</b> dabayein.','<b>Library ID</b> aur <b>PIN</b> daalein. Pichhle din ka backup wapas aa jayega (logo bhi).','Ya <b>Backup by date</b> se pichhle 60 din me se koi bhi din chunkar Restore karein.'))
a(box('danger','Kabhi na karein','<ul><li><b>LibraryData</b> folder delete na karein (ye aapka poora data hai).</li><li>Computer ki date / time galat na rakhein — ERP license check kar leta hai.</li><li>PIN aur Library ID kisi ko na batayein.</li></ul>'))

a('<h1>14. Online View — phone par hisaab</h1><p>Aap ghar baithe apni library ka aaj ka hisaab dekh sakte hain.</p>')
a(steps('Phone ke Chrome me ye address kholein: <code>https://setu-erp.theinkthreadhub.workers.dev/view</code>','<b>Library ID</b> (jaise SETU-0012) aur apna <b>PIN</b> daalein.','Dikhega: aaj ki fee, kharcha, profit, kaun aaya (IN/OUT), due list aur 7 din ka chart.','Neeche <b>Install</b> dabakar ise home screen par app bana lein.'))
a(box('info','Plan','Online View aapke plan me ON hona chahiye. PIN galat 5 baar daalne par 1 ghante ke liye band ho jata hai.'))

a('<h1>15. License renew aur Setu Pro ke message</h1>')
a(fig('d_license','License screen: kab tak chalega, aur kitna samay bacha.',1000))
a(ul('Upar patti me <b>License: kitne din bache</b> dikhta hai. <b>Khatam hone se pehle</b> Setu Pro ko batayein.','<b>Renew:</b> Setu Pro payment lekar <b>cloud se</b> nayi key bhej dega. ERP internet milte hi <b>khud activate</b> ho jata hai — aapko kuch nahi karna. (Na ho to License screen par key paste karein.)','Aakhri 48 ghante me live countdown dikhta hai.'))
a(box('warn','Setu Pro ke message / lock','Setu Pro aapko ERP me <b>message (popup)</b> bhej sakta hai. Payment baaki rehne par <b>⚠ warning patti</b> ya <b>🔒 lock</b> bhi laga sakta hai. Lock me bhi aapka <b>data hamesha safe</b> rehta hai; payment ke baad Setu Pro lock hata deta hai aur app wapas chalne lagta hai.'))

a('<h1>16. Help & Support</h1>')
a(fig('d_help','Utilities → Help & Support: ticket banayein, jawab isi screen par aata hai.',1000))
a(steps('<b>Utilities → Help & Support</b>.','<b>Subject</b> aur apna <b>message</b> likhein (kya hua, kab hua) → bhejein. Internet zaroori hai.','Jawab isi screen par dikhta hai. Jaldi ho to <b>WhatsApp Setu Pro</b> button.'))
a(box('tip','Setu Pro Customer Support','📞 <b>6392995127</b> · ✉️ setuproindia@gmail.com · 🌐 www.setupro.in'))

a('<h1>17. Aksar aane wali dikkatein</h1>')
a(table(['Dikkat','Kya karein'],[
 ['ERP nahi khul raha (computer)','Desktop icon se dobara kholein. Chhoti kaali window pehle se khuli ho to wahi khuli rehne dein. Phir bhi na khule to computer restart karke try karein.'],
 ['"License expired / not active"','Machine code Setu Pro ko bhejein → nayi key → Activate. Pehle <b>Check cloud renewal</b> bhi dabakar dekhein.'],
 ['"Clock / date" ka message','Computer ki date aur time sahi karein.'],
 ['Upar "● Saved offline"','Internet nahi hai. Data safe hai. Internet aate hi apne aap sync ho jayega ya <b>Sync now</b> dabayein.'],
 ['Laal patti: "Data save NAHI hua"','Disk bhar gayi ho ya folder par permission na ho. Computer me jagah banayein, ERP dobara kholein. Na theek ho to Setu Pro ko turant batayein.'],
 ['Receipt print nahi / kat rahi hai','Settings me <b>Slip size</b> printer ke hisaab se chunein → <b>Test print</b>.'],
 ['WhatsApp nahi khul raha','Settings → <b>Open WhatsApp in</b>: WhatsApp Web ya App badal kar dekhein. Student ka mobile number sahi hai ya nahi dekhein.'],
 ['Student ka link "not valid"','Link purana ho sakta hai. Student Record → <b>Share link</b> se naya bhejein. Student app aapke plan me ON hona chahiye.'],
 ['Student ki attendance ERP me der se aayi','Normal hai — ERP har ~3 minute me cloud se leta hai. Internet chalu rakhein.'],
 ['Student app me "Mark IN first" / "Already marked"','Din me ek IN aur ek OUT hi hota hai. Pehle IN lagana zaroori hai. Naye din apne aap saaf ho jata hai.'],
 ['Student app me purana data dikh raha','Student ka page refresh karein. Aapka ERP internet par chalu hona chahiye.'],
 ['Naya computer / phone','Chapter 13: Restore from cloud (Library ID + PIN).']]))

a('<h1>18. Roz ka routine aur Do / Don\'t</h1>')
a('<div class="cols"><div><h3>🌅 Subah</h3>'+ul('ERP kholein, upar <b>● Synced</b> dekhein.','Due popup dekhein.','Message ya lock ka banner ho to padhein.')+'<h3>☀️ Din me</h3>'+ul('Naya student: <span class="k">Alt+S</span>','Fee: <span class="k">Alt+C</span> → receipt → WhatsApp','Attendance: <span class="k">Alt+A</span> (ya students khud app se)','Kharcha: <span class="k">Alt+E</span>')+'</div><div><h3>🌙 Shaam</h3>'+ul('<b>Day Book (B)</b> se cash match karein.','Due wale students ko <b>Fee Reminder (Z)</b>.','Zarurat ho to students ko <b>message</b>.','ERP band karne se pehle ek baar <b>Sync now</b>.')+'<h3>📅 Mahine me ek baar</h3>'+ul('<b>Income vs Expense (V)</b> dekhein.','License / payment date check karein.','Backup folder / Drive check karein.')+'</div></div>')
a(table(['✅ Karein','❌ Na karein'],[['Cloud PIN set karein aur likh kar rakhein','LibraryData folder delete / rename'],['Hamesha receipt se paisa lein, receipt WhatsApp / print karein','Receipt banaye bina fee lena'],['Galti ho to Delete karke dobara bhariye (confirm ke baad)','Computer ki date badalna'],['Naya version aaye to install karein (data safe)','Key / PIN / Library ID kisi ko batana'],['Kuch samajh na aaye to 6392995127','Window band karke ERP chhodna (sirf minimize)']]))
a('<p style="margin-top:8mm" class="small">Is guide ke baare me sujhav ho to Setu Pro ko batayein. · Setu Pro · 6392995127 · setuproindia@gmail.com</p>')

if __name__ == '__main__':
    import sys
    html = page(''.join(B), 'Library ERP — User Guide')
    open(sys.argv[1] if len(sys.argv) > 1 else 'client_body.html', 'w', encoding='utf-8').write(html)
    open('client_cover.html', 'w', encoding='utf-8').write(cover('Library ERP<br>Use Karne Ki Guide', 'Install se lekar fee, attendance, student app, backup aur renewal tak — step by step, asli screens ke saath.', 'Library owner / operator ke liye'))
    print('html ok', len(html) // 1024, 'KB')
