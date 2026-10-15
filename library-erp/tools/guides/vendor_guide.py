from common import *
B = []
a = B.append
a('<h1 class="first">Setu Pro Team Guide</h1><p class="lead">Ye guide <b>Setu Pro ki team</b> (Ankit Sharma, Surya Tiwari aur support) ke liye hai: customer ko software bechna, activate karna, payment aur renewal sambhalna, features on/off karna, support dena, aur cloud ko surakshit rakhna.</p>')
a('<div class="card3"><div><b>🔑 Keygen</b>Activation key banata hai (phone app ya computer exe). Sirf aapke paas.</div><div><b>🛡️ Super Admin</b>Saari libraries ek jagah: payment, license, lock, message, features, support.</div><div><b>☁️ Cloud</b>Cloudflare par backup, student app, Online View. GitHub se apne aap update hota hai.</div></div>')
a('<h2>Chapters</h2><table class="toc">' + ''.join(f'<tr><td class="n">{n}</td><td>{t}</td></tr>' for n, t in [(1,'Poora system ek nazar me'),(2,'Naye customer ko onboard karna (15 minute)'),(3,'Keygen — key banana'),(4,'Super Admin — roz ka kaam'),(5,'Plans aur features'),(6,'Renewal aur payment process'),(7,'Support — ticket aur aam samasyayein'),(8,'Cloud, update aur suraksha'),(9,'Free plan ki seema aur kab upgrade karein'),(10,'Zaroori rules aur quick reference')]) + '</table>')
a(box('danger','Sabse zaruri','<ul><li><b>private_key.pem</b>, Android keystore (<code>.p12</code>) aur uska password, aur <code>LibraryKeys.csv</code> ka <b>offline backup</b> (pen drive + doosri jagah) rakhein. Inke bina naye keys / APK updates nahi ban sakte.</li><li>Ye files kabhi customer, WhatsApp ya GitHub par na bhejein.</li></ul>'))

a('<h1>1. Poora system ek nazar me</h1>')
a(table(['Hissa','Kya hai','Kaun use karta hai'],[
 ['<b>Library ERP</b> (exe / APK)','Library ka main software. Offline chalta hai, data local rakhta hai, internet par cloud sync.','Library owner'],
 ['<b>Student App</b>','Har student ke private link se: IN/OUT, fee, attendance, streak, messages. Home screen par library ke naam/logo se install.','Students'],
 ['<b>Online View</b>','Owner ka phone dashboard (<code>/view</code>), Library ID + PIN.','Library owner'],
 ['<b>SetuKeygen</b>','Activation key banata hai (phone: SetuKeygen.apk, computer: LibraryKeygen.exe).','Setu Pro team'],
 ['<b>SetuAdmin</b> (Super Admin)','Saari libraries manage karne ka app (<code>/super</code> page bhi).','Setu Pro team'],
 ['<b>Cloud</b>','Cloudflare Worker + D1 database. URL: <code>https://setu-erp.theinkthreadhub.workers.dev</code>','Apne aap']]))
a('<h2>Ek customer ka safar</h2>')
a(steps('<b>Sale</b> → customer ko exe / APK deni, plan tay karna (Basic / Standard / Pro).','<b>Activation</b> → customer ka Machine code → Keygen se key → customer paste karta hai.','<b>Setup</b> → library ki details, logo, fee plans (chapter 2).','<b>Roz ka use</b> → ERP cloud se judta hai; Admin me library ka Installed date, students, backup status dikhta hai.','<b>Payment record</b> → Admin me Payment (paid till, plan, amount).','<b>Renewal</b> → license khatam hone se 5 din pehle Admin warning deta hai → payment → Renew se nayi key cloud se bhejna.','<b>Support</b> → tickets, WhatsApp, call.'))

a('<h1>2. Naye customer ko onboard karna (15 minute)</h1>')
a(table(['#','Kaam','Kahan'],[['1','Customer ke computer / phone par ERP install: exe ya APK (Windows "Run anyway" bataein)','Customer device'],['2','Machine code lein → Keygen se key banayein → WhatsApp par bhejein','Keygen'],['3','Customer key paste karke <b>Activate</b> kare. ERP kholte hi library ka naam / contact daalein','ERP'],['4','Settings me <b>logo upload</b> (student app ke icon ke liye zaroori), slip size, "After saving a receipt"','ERP → Settings'],['5','<b>Fee Master</b> me plans (30 din = monthly, 0 = ek baar), <b>Session</b> sahi','ERP'],['6','Students daalna: New Admission ya Excel Bulk Import','ERP'],['7','<b>Cloud PIN set</b> karwayein (4–6 ank) aur <b>Library ID</b> likhwa lein. Upar ● Synced hara dikhe','ERP → Settings'],['8','Ek test receipt + WhatsApp + attendance karwa kar dikhayein','ERP'],['9','Student app: ek student ka link banakar apne phone par test karwayein (agar plan me hai)','ERP → Student Record'],['10','Admin me library dikh rahi hai? <b>Payment</b> bharein, <b>Plan / Features</b> set karein','Super Admin'],['11','Customer ko <b>Client Guide PDF</b> dein aur support number 6392995127','—']]))
a(box('tip','Customer ko ye 3 baatein zaroor batayein','<ol><li>ERP ki chhoti window band na karein, sirf minimize.</li><li>Cloud PIN aur Library ID likh kar rakhein.</li><li>Kuch atke to pehle Help & Support / 6392995127.</li></ol>'))

a('<h1>3. Keygen — key banana</h1><p>Key <b>machine se bandhi</b> hoti hai: ek key sirf us computer / phone par chalti hai jiska Machine code diya gaya. Key ke andar Machine code, banne ki date, khatam hone ki date, plan aur library ka naam hota hai.</p>')
a('<h2>Phone par (SetuKeygen.apk)</h2>')
a(row(['k_setup','k_form','k_result'],['Pehli baar: private_key.pem chunein aur PIN set karein','Machine code, library naam aur plan chunein','Key taiyar: Copy / WhatsApp / Share'],340,'row3'))
a(steps('<b>Pehli baar</b>: <b>Choose private_key.pem</b> se apni private key file chunein (key app ke andar surakshit rehti hai) aur <b>4–6 ank ka PIN</b> set karein. Phir <b>Save & open</b>.','Har baar PIN daalkar kholein. 5 galat PIN par 15 minute ka lock.','<b>Machine code</b> daalein (customer ki activation screen par dikhta hai, format <code>XXXXX-XXXXX</code>).','<b>Library name</b> likhein (record ke liye).','<b>Plan</b> chunein: 1 Month, 3 Months, 6 Months, 1 Year, <b>Lifetime</b>, ya <b>Custom</b> (minute / ghante / din — demo ke liye 10 din).','<b>Generate key</b> dabayein. Neeche key aati hai: <b>Copy</b>, <b>WhatsApp</b> (customer ka number daalne par seedha us chat me) ya <b>Share</b>.','Neeche <b>Keys made</b> list me purane keys milte hain; <b>Export CSV</b> se pura record (<code>LibraryKeys.csv</code>) nikaal sakte hain.'))
a('<h2>Computer par (LibraryKeygen.exe)</h2><p>Wahi kaam command window me. private_key.pem usi folder me rakhein. Record <code>LibraryKeys.csv</code> me judta rehta hai.</p>')
a(table(['Plan / duration','Kab dein'],[['5 min / 2 h / 10 d (Custom)','Demo, test, trial'],['1m / 3m / 6m / 1y','Normal paid plan'],['<b>Lifetime</b>','Sirf bahut sochkar. Lifetime key us machine par hamesha chalti hai']]))
a(box('warn','Lifetime galti se de di to?','Nayi key (chhota plan) Admin → Renew se bhejne par purani Lifetime ki jagah nayi key lag jati hai (Admin me Lifetime warning dikhti hai). Par agar customer ke paas purani key ki copy hai to wo bhi us machine par chalti rahegi — isliye Lifetime sirf bharose ke customer ko dein.'))

a('<h1>4. Super Admin — roz ka kaam</h1><p>Phone par <b>SetuAdmin.apk</b> ya browser me <code>…workers.dev/super</code>. Login password wahi jo Cloudflare me <code>ADMIN_PASSWORD</code> secret hai (<b>Remember on this device</b> se yaad rakh sakte hain).</p>')
a(row(['a_login','a_home'],['Login: Admin password','Home: upar 4 ginti, neeche har library ka card'],420))
a('<h2>Upar ke 4 box (tap karke filter lagta hai)</h2>')
a(table(['Box','Matlab'],[['Libraries','Kul libraries'],['Backup stale','Jinka cloud backup purana ho gaya (ERP band / net nahi)'],['License ≤5d / expired','License 5 din me khatam ya khatam ho chuka — renewal chahiye'],['Payment due ≤5d','Payment ki date 5 din me aane wali ya nikal chuki']]))
a('<h2>Library ka card</h2>')
a(ul('<b>Naam, Library ID</b> (tap = copy), contact, <b>📞 Call</b> / <b>💬 WhatsApp</b>.','Laal / peeli patti: <b>Payment overdue</b> ya <b>Next payment due</b>.','<b>Installed</b> (install ki date), <b>Students</b> (active/kul), <b>Receipts</b>, <b>App version</b>.','<b>Last payment</b> (₹ + plan), <b>Next payment</b> (date), <b>License</b> (kitne din bache), <b>Backup</b> (kab hua).','Tag: <b>Restore PIN not set</b> (customer ne cloud PIN nahi banaya), <b>Plan</b>, <b>Off: …</b> (band feature).','Sabse urgent libraries (expire / payment) <b>upar</b> aati hain.'))
a('<h2>Buttons — kya karte hain</h2>')
a(table(['Button','Kaam'],[
 ['<b>Renew</b>','Naya Activation Key paste karke "Send to library" — ERP net milte hi khud activate (expire hone ke baad bhi)'],
 ['<b>Payment</b>','Paid till (agli payment date), plan, amount, note — Admin ka hisaab'],
 ['<b>⚙ Features</b>','Plan chunein ya har feature ka switch (chapter 5)'],
 ['<b>✉ Message</b>','Library ke ERP me popup message'],
 ['<b>🔒 Lock</b>','Normal / ⚠ Warning patti / 🔒 Lock'],
 ['<b>Tickets</b>','Us library ke support tickets'],
 ['<b>Backup</b>','Latest cloud backup download / save'],
 ['<b>Set PIN</b>','Library ka Online View / restore PIN naya set karna'],
 ['<b>Delete</b>','Library cloud se hataana (type-to-confirm). Option: <b>Block this computer</b>']]))
a(row(['a_pay','a_renew'],['Payment: agli payment date, plan, amount','Renew: machine code copy, key paste, "Send to library"'],420))
a(row(['a_notice','a_lock'],['Message: ERP me popup','Lock: Normal / Warning / Lock'],420))
a(row(['a_features','a_delete'],['Features: Basic / Standard / Pro ya alag switch','Delete: Library ID likhkar confirm; Block option'],420))
a(box('info','Lock ke levels','<b>Normal</b> — sab chalu. <b>⚠ Warning</b> — ERP ke upar patti (payment yaad dilane ke liye). <b>🔒 Lock</b> — ERP band, lock screen par Setu Pro ka WhatsApp / Call. <b>Data hamesha safe rehta hai.</b> Payment aate hi <b>Normal</b> karein — ~3 minute me app wapas chalu.'))
a(box('warn','Delete ke bare me','Delete karne par library ke cloud backups, photos aur tickets <b>hamesha ke liye</b> hat jate hain (wapas nahi aate). Customer ke computer / phone ka apna data safe rehta hai. <b>Block this computer</b> chunne par wo machine dobara register nahi ho paati. Delete se pehle <b>Backup</b> button se latest backup download kar lein. Block hataana ho to neeche <b>🚫 Blocked → Unblock</b>.'))

a('<h1>5. Plans aur features</h1>')
a(box('info','Ye sujhaye gaye (recommended) plans hain','Daam aur plan ka final faisla aapka hai. Admin ke presets abhi 3 hain; features alag-alag bhi on/off ho sakte hain.'))
a(table(['Plan','Daam (mahina / saal)','Features'],[['<b>Basic</b>','₹499 / ₹4,990','Core ERP (students, fee, receipt, attendance, kharcha, reports) + Cloud backup + Bulk Import'],['<b>Standard</b>','₹799 / ₹7,990','Basic + WhatsApp, Fee Reminder, Online View'],['<b>Pro</b>','₹1,199 / ₹11,990','Standard + Student App + Books']]))
a(table(['Feature (switch)','Kya band hota hai','Kaun rokta hai'],[['Student app','Student link / app, Student Messages','Cloud (server) rokta hai'],['Online View','Owner ka phone dashboard','Cloud rokta hai'],['Cloud backup','Backup / restore','Cloud rokta hai'],['WhatsApp, Books, Fee Reminder, Bulk Import','ERP me menu / button hat jate hain','ERP (customer ke device par — tamper karna thoda aasaan)']]))
a(ul('Feature save karne ke ~1 minute me library ko lagu ho jata hai (ERP ki agli cloud poll par).','Off feature ka menu ERP se hat jata hai; seedha kholne par "plan me nahi hai" + upgrade ka button.','Naye library par sab ON hota hai jab tak aap preset na chunein.'))

a('<h1>6. Renewal aur payment process</h1>')
a('<h2>License renew (key se)</h2>')
a(steps('Admin me <b>License ≤5d / expired</b> box dabakar list dekhein (ya library card par License din).','Customer se <b>payment</b> lein → Admin → <b>Payment</b> me record karein (paid till, plan, amount).','Library card → <b>Renew</b> → <b>Machine code Copy</b> → Keygen me us machine ke liye <b>nayi key</b> banayein (plan chunein).','Key ko Renew ke box me <b>paste</b> → <b>Send to library</b>.','ERP internet milte hi key khud laga leta hai (customer ko kuch nahi karna). Card par "a key is waiting to apply" dikhta hai jab tak lagi nahi.'))
a('<h2>Payment nahi aayi to</h2>')
a(table(['Din','Kya karein'],[['Date se 5 din pehle','Admin warning dikhata hai → customer ko WhatsApp / call'],['Date nikal gayi','<b>✉ Message</b> bhejein (nicha ka sample) → <b>🔒 Lock → ⚠ Warning</b>'],['Kuch din baad','<b>🔒 Lock</b> (lock message me apna number). Data safe — customer ko pata chalta hai ki payment baaki hai'],['Payment aa gayi','Payment record karein → Lock <b>Normal</b> → (license ho to Renew)']]))
a(box('tip','Sample message','"Namaste, aapka Library ERP ka license / payment <date> ko khatam ho raha hai. Renew ke liye 6392995127 par sampark karein. — Setu Pro"'))

a('<h1>7. Support — ticket aur aam samasyayein</h1>')
a(row(['a_tickets'],['Tickets: library ka message aur aapka jawab'],420))
a(steps('Home ke neeche <b>🎫 Tickets</b> (laal number = naye / unread).','Ticket kholkar jawab likhein. Library ke ERP (Utilities → Help & Support) me wahi jawab dikhta hai. Turant madad ke liye customer WhatsApp / call bhi karta hai.','Samasya hal hone par ticket <b>close</b> karein.'))
a(table(['Samasya','Wajah / Hal'],[
 ['"License expired" / "not active"','Machine code lekar nayi key. Ya Admin → Renew se bhej dein (ERP khud laga lega).'],
 ['"Cloud link is not valid — connect again"','Cloud ko library ki pehchaan nahi mili (library delete hui ya reset). ERP khud dobara register ho jata hai aur <b>naya Library ID</b> milta hai — purane student links aur Online View ID badal jate hain. Customer ko naya ID aur naye links dene padenge. (Agar Block lagaya hai to register nahi hoga.)'],
 ['Backup stale / Synced nahi','Customer ka internet / ERP band. Customer se ERP kholne aur Sync now ko kahein.'],
 ['Customer ne PIN bhool gaya','Admin → <b>Set PIN</b> se naya PIN set karke batayein.'],
 ['Student app nahi chal raha / link invalid','Plan me Student app ON hai? Student Record se Share link naya bhejein. Link badalna ho to ERP me <b>♻ New link</b>.'],
 ['Student ki attendance ERP me nahi aayi','ERP har ~3 minute me leta hai. ERP internet par ON ho. Phir bhi nahi to customer se Sync now.'],
 ['Naya computer / data kho gaya','Nayi key + ERP me <b>Restore from cloud</b> (Library ID + PIN). Admin → Backup se bhi file nikaal sakte hain.'],
 ['Admin me library nahi dikh rahi','ERP ne abhi tak cloud se connect nahi kiya (internet / cloud URL). Settings → Sync now.'],
 ['Receipt print / WhatsApp problem','Client Guide ka chapter 17 dekhein (slip size, Open WhatsApp in).'],
 ['Customer ne Lifetime ki jagah plan badalna','Chapter 3 ka Lifetime wala box.']]))

a('<h1>8. Cloud, update aur suraksha</h1>')
a('<h2>Cloud kaise update hota hai</h2>')
a(steps('Code badlav hone par <b>GitHub</b> (branch <code>liberp</code>) par push hota hai.','<b>Actions → "Setu Cloud Worker deploy"</b> apne aap chalta hai: page jodna, syntax check, <b>smoke test</b> (38 jaanch), phir Cloudflare par deploy. Hara ✅ = live (~1 minute).','Cloudflare dashboard me <b>kuch paste / badalna nahi</b> hai. Database aur ADMIN_PASSWORD waise hi rehte hain.','ERP ya APK badla ho to naya <b>exe / APK</b> customers ko dena padta hai (data safe rehta hai). <b>Pehle worker deploy, phir ERP update.</b>'))
a(box('warn','Deploy laal ❌ ho to','GitHub → Actions → us run par click → laal step ka log dekhein. Test fail = code me galti (live nahi hua, purana worker chal raha hai). "Authentication" error = Cloudflare token / Account ID (GitHub Secrets). Kuch samajh na aaye to developer ko log bhejein. Galat deploy ko wapas karne ke liye: <code>npx wrangler rollback</code> (pichhla version).'))
a('<h2>Backup jo aap rakhein</h2>')
a(table(['Kya','Kahan','Kitni baar'],[['<b>D1 database export</b>','GitHub Actions "D1 weekly export" (artifact, 60 din). Iske liye Cloudflare token me <b>D1 permission</b> chahiye','Har Sunday apne aap'],['<b>private_key.pem</b>','Offline (2 jagah, pen drive + surakshit jagah)','Ek baar, phir sambhal kar'],['<b>Keystore (.p12) + password</b>','Offline. Isse hi APK updates sign hote hain','Ek baar'],['<b>LibraryKeys.csv</b>','Offline + Keygen "Export CSV"','Mahine me ek baar'],['Admin → library <b>Backup</b>','Kisi library ka latest backup haath se','Zarurat par']]))
a('<h2>GitHub Secrets (ek baar ki setting)</h2>')
a(ul('<b>CLOUDFLARE_API_TOKEN</b> — Cloudflare → My Profile → API Tokens → "Edit Cloudflare Workers" template (D1 export ke liye D1 permission jodein).','<b>CLOUDFLARE_ACCOUNT_ID</b> — Cloudflare → Workers & Pages → Account ID.','Repo → Settings → Secrets and variables → Actions me daalein. <b>Token kisi ko na bhejein.</b>'))

a('<h1>9. Free plan ki seema aur kab upgrade karein</h1><p>Lakshya: <b>100 libraries × 100 students</b> Cloudflare ke <b>free plan</b> par. Local load test me ye fit baitha hai (poora hisaab <code>docs/CAPACITY.md</code> me).</p>')
a(table(['Seema (free)','Hamara anuman (100 × 100, busy din)','Upyog'],[['Worker requests / din: 1,00,000','~78,000','<b>78%</b> (sabse tight)'],['D1 rows written / din: 1,00,000','~66,000','66%'],['D1 rows read / din: 50 lakh','~8 lakh','16%'],['D1 storage: 5 GB','~0.4 GB','8%']]))
a(ul('Ek library ka cloud data ≈ <b>3–5 MB</b> (30 din ke backup + students ki rows). Backup roz ka ~100 KB (100 students).','ERP har <b>3 minute</b> me cloud se poochta hai; sirf badle hue students cloud par jate hain.'))
a(box('warn','Kab Workers Paid ($5/mahina) lein','Jab libraries 100 ke paas pahunchein, ya Cloudflare dashboard me requests / din 85,000 ke upar jayein. Tab ek hi click me limits bahut badh jati hain. Tab tak: poll 3 → 5 minute karne se ~96 requests/library/din bachti hain.'))

a('<h1>10. Zaroori rules aur quick reference</h1>')
a(table(['Cheez','Detail'],[['Support number','<b>6392995127</b> (Ankit: 8445298117)'],['Email / Site','setuproindia@gmail.com · www.setupro.in'],['Cloud URL','https://setu-erp.theinkthreadhub.workers.dev'],['Owner phone dashboard','…/view'],['Super Admin','…/super (ya SetuAdmin.apk)'],['Student page','…/s/&lt;LibraryID&gt;~&lt;token&gt;'],['Files','LibraryERP-Setup-vX.exe, LibraryERP-vX.apk, SetuStudent.apk, SetuAdmin.apk, SetuKeygen.apk, LibraryKeygen.exe'],['Code / docs','GitHub repo <code>hotel-erp</code> → <code>library-erp/</code> (AGENTS.md, docs/…)']]))
a('<div class="cols"><div><h3>✅ Karein</h3>'+ul('Har naye customer ka <b>Payment</b> aur <b>next payment date</b> Admin me bharein.','Key banate waqt library ka naam likhein (record ke liye).','Customer ko <b>Cloud PIN</b> set karwayein.','Delete se pehle <b>Backup</b> download.','Naya ERP version aaye to customers ko batayein.')+'</div><div><h3>❌ Na karein</h3>'+ul('private_key.pem / keystore / token / Admin password kisi ko bhejna.','Bina soche <b>Lifetime</b> key.','Delete + Block bina confirm karke.','Worker ko dashboard me haath se badalna (GitHub se hi).','Customer ka data / link kisi aur ko dikhana.')+'</div></div>')
a('<p class="small" style="margin-top:8mm">Customer ko dene ke liye alag guide: <b>Library ERP — Use Karne Ki Guide</b>.</p>')

if __name__ == '__main__':
    import sys
    open(sys.argv[1] if len(sys.argv) > 1 else 'vendor_body.html', 'w', encoding='utf-8').write(page(''.join(B), 'Setu Pro Team Guide'))
    open('vendor_cover.html', 'w', encoding='utf-8').write(cover('Setu Pro<br>Team Guide', 'Keygen, Super Admin, plans, renewal, support aur cloud — poora vendor playbook.', 'Setu Pro team ke liye (andar ki jaankari)'))
    print('html ok')
