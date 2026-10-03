"""Fictional, deterministic five-second market observations. Replace with a real feed adapter later."""
def price(symbol, tick):
    # Hand-authored, fictional scenarios. BOLT goes 100x and crashes within 30 minutes.
    knots = {'SCOUT':[(0,1),(15,.7),(40,1.1),(90,1.9),(150,1.3),(240,2.4),(360,1.8)],
             'BOLT':[(0,.01),(20,.009),(50,.02),(100,.15),(180,1),(192,.004),(360,.003)],
             'DUST':[(0,.1),(30,.13),(80,.08),(140,.04),(240,.06),(360,.025)]}[symbol]
    for (a,x),(b,y) in zip(knots,knots[1:]):
        if tick<=b:
            return x+(y-x)*(tick-a)/(b-a)
    return knots[-1][1]


def liquidity(symbol,tick):
    return 0 if symbol=='BOLT' and tick>=192 else (4000 if symbol=='DUST' else 80000)

