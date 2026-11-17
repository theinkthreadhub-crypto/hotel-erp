// Setu aggregator adapter. No network access, no mock orders, and no provider credentials here.
// Parse only field names actually furnished by the approved POS partner's webhook contract.
const text=(v,n=100)=>String(v??'').trim().slice(0,n);
const num=(v)=>v===null||v===undefined||v===''?NaN:Number(v);
export function normalizeAggregatorOrder(platform,payload){
  if(!['zomato','swiggy'].includes(platform))throw new Error('Unknown provider');
  if(!payload||typeof payload!=='object'||Array.isArray(payload))throw new Error('Expected order object');
  const order=payload.order && typeof payload.order==='object'&&!Array.isArray(payload.order) ? payload.order : payload;
  const orderId=text(order.order_id ?? order.orderId ?? order.id,90);
  const outletId=text(order.restaurant_id ?? order.restaurantId ?? order.store_id ?? order.storeId ?? order.outlet_id ?? order.outletId,80);
  if(!/^[A-Za-z0-9][A-Za-z0-9._-]{1,89}$/.test(orderId))throw new Error('Missing/invalid partner order ID');
  if(!/^[A-Za-z0-9][A-Za-z0-9._-]{1,79}$/.test(outletId))throw new Error('Missing/invalid partner outlet ID');
  const list=Array.isArray(order.order_items)?order.order_items:
    Array.isArray(order.items)?order.items:
    Array.isArray(order.order_details?.items)?order.order_details.items:[];
  if(list.length>100)throw new Error('Order too large');
  const problems=[];
  if(!list.length)problems.push('No recognizable item list: partner payload mapping required');
  const items=list.map((x,index)=>{
    if(!x||typeof x!=='object')throw new Error('Bad item');
    const title=text(x.name ?? x.item_name ?? x.title,100);
    const externalId=text(x.item_id ?? x.itemId ?? x.id ?? x.sku,80);
    const qty=num(x.quantity ?? x.qty);
    const rawPrice=num(x.price ?? x.unit_price ?? x.unitPrice);
    if(!title)problems.push('Missing item name at row '+(index+1));
    if(!Number.isFinite(qty)||qty<=0||qty>200)problems.push('Invalid item quantity '+(index+1));
    if(!Number.isFinite(rawPrice)||rawPrice<0||rawPrice>1e7)problems.push('Price mapping needed '+(index+1));
    return {externalId,name:title||'Unmapped item',qty:Number.isFinite(qty)&&qty>0&&qty<=200?qty:0,
      price:Number.isFinite(rawPrice)&&rawPrice>=0?Math.round(rawPrice*100)/100:0};
  });
  const totalValue=num(order.order_total ?? order.total ?? order.total_amount ?? order.amount);
  if(!Number.isFinite(totalValue)||totalValue<0||totalValue>1e9)problems.push('Confirm total from provider');
  const note=text(order.special_instructions ?? order.instructions ?? order.note,250);
  const externalStatus=text(order.order_status ?? order.status ?? 'placed',40).toLowerCase();
  if(/cancel|reject|fail|expire|timeout|deliver|complete/.test(externalStatus))
    problems.push('Order is not newly actionable: provider status '+externalStatus);
  return {
    platform,orderId,outletId,items,total:Number.isFinite(totalValue)&&totalValue>=0?Math.round(totalValue*100)/100:0,
    note,externalStatus,at:Date.now(),needsReview:problems.length>0,
    issues:problems.slice(0,15),source:'authenticated_partner_webhook'
  };
}
export function outletHotel(env,platform,outletId){
  let config;
  try{config=JSON.parse(env.AGGREGATOR_OUTLET_MAP||'{}');}catch(e){throw new Error('Partner outlet mapping misconfigured');}
  const code=String(config[platform+':'+outletId]||'').toUpperCase();
  return /^[A-Z0-9]{4,12}$/.test(code)?code:'';
}
