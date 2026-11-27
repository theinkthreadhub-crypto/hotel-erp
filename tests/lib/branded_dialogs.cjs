// The app's questions are branded dialogs now (#ui-dlg), not the browser's confirm / prompt. A test that answered the
// browser dialog (page.on('dialog', d => d.accept() / d.dismiss())) answers the branded one the same way with this.
function script(answer){
  const click = () => {
    const b = document.getElementById(answer === 'accept' ? 'ui-dlg-yes' : 'ui-dlg-no') || document.getElementById('ui-dlg-yes');
    if(b && document.getElementById('ui-dlg') && document.getElementById('ui-dlg').classList.contains('open')) b.click();
  };
  const start = () => new MutationObserver(() => setTimeout(click, 0)).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
  if(document.documentElement) start(); else document.addEventListener('DOMContentLoaded', start);
}
async function answerBrandedDialogs(page, answer = 'accept'){
  await page.addInitScript(script, answer);
  try{ if(page.url() && page.url() !== 'about:blank') await page.evaluate(script, answer); }catch(e){}
}
module.exports = { answerBrandedDialogs };
