// Native dialogs keep keyboard focus inside and restore it when closed (Esc).
document.querySelectorAll('[data-open-dialog]').forEach(button=>{
 button.onclick=()=>{
  const dialog=document.getElementById(button.dataset.openDialog);
  if(!dialog.open)dialog.showModal();
 };
});
