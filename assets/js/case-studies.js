(function(){
 'use strict';
 const root=document.querySelector('.case-page');
 if(!root)return;
 const cards=Array.from(root.querySelectorAll('.case-card'));
 const input=root.querySelector('#case-search'),result=root.querySelector('#case-results');
 let kind='all',category='all';
 function render(){
  const query=input.value.trim().toLocaleLowerCase();let count=0;
  cards.forEach(card=>{const match=(kind==='all'||card.dataset.kind===kind)&&(category==='all'||card.dataset.categories.split(' ').includes(category))&&(!query||card.textContent.toLocaleLowerCase().includes(query));card.hidden=!match;if(match)count++;});
  root.querySelectorAll('[data-kind-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.kindFilter===kind)));
  root.querySelectorAll('[data-category-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.categoryFilter===category)));
  result.textContent=count+' '+result.dataset.countLabel;
  root.querySelector('.case-empty').hidden=count!==0;
 }
 root.querySelectorAll('[data-kind-filter]').forEach(button=>button.addEventListener('click',()=>{kind=button.dataset.kindFilter;render();}));
 root.querySelectorAll('[data-category-filter]').forEach(button=>button.addEventListener('click',()=>{category=button.dataset.categoryFilter;render();}));
 input.addEventListener('input',render);
 root.querySelector('.case-reset').addEventListener('click',()=>{kind='all';category='all';input.value='';render();input.focus();});
 render();
})();
