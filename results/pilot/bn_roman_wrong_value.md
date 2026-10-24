# bn_roman rows labeled wrong_value (primary metric, lenient format)

gold = accepted values (first 3 shown); predicted = what the model wrote. BANGLA-WORD? = predicted text contains a word from the Bangla-form query that is not in the English query.

## Qwen3-1.7B (None): 3 rows

| item | bn_roman query | en correct? | param | gold | predicted | note |
|---|---|---|---|---|---|---|
| 196 | 2022/08/16 tarikh e London er air quality index koto chhilo? | NO | date | 08-16-2022 | "2022/08/16" |  |
| 304 | shesh basketball match e 'LeBron James' koto point ar rebound peyechhilen tar hishab dao. | NO | team | Los Angeles Lakers / LAL / Lakers | "Boston Celtics" |  |
| 360 | 500 calories er kom hobe emon pasta carbonara toirir ekta recipe khuje dao. | yes | recipeName | pasta carbonara | "500 calories er kom hobe emon pasta carbonara toirir ekta recipe khuje dao" | BANGLA-WORD? |
| 360 | 500 calories er kom hobe emon pasta carbonara toirir ekta recipe khuje dao. | yes | maxCalories | 500 | (missing) |  |

## Qwen3-4B (template): 5 rows

| item | bn_roman query | en correct? | param | gold | predicted | note |
|---|---|---|---|---|---|---|
| 205 | garite kore Boston theke New York jaowar rastay ekhon traffic er obostha kemon jene dao. | yes | start_location | Boston | "Garite Kore" | BANGLA-WORD? |
| 205 | garite kore Boston theke New York jaowar rastay ekhon traffic er obostha kemon jene dao. | yes | end_location | New York / NYC | "Boston" |  |
| 394 | Eiffel Tower theke Louvre Museum er durottwo koto ar jete kotokkhon shomoy lagbe? | yes | traffic | False | true |  |
| 286 | agami mashe (April 2022) San Diego te shongitshilpi Beyonce r je concert hobe tar bistarito janao. | yes | artist | Beyonce | "agami mashe" | BANGLA-WORD? |
| 357 | vegan chocolate cake bananor recipe dao, dhape dhape. | yes | dish_name | chocolate cake / vegan chocolate cake | "vegan chocolate cake bananor" | BANGLA-WORD? |
| 328 | 'Ticket to Ride' board game tir rating ar kotojon khelowar eksathe khelte paren ta ber koro. | yes | parameters | ['rating', 'player count'] / ['player count', 'rating'] | ["rating"] |  |
| 328 | 'Ticket to Ride' board game tir rating ar kotojon khelowar eksathe khelte paren ta ber koro. | yes | language | English | "en" |  |

## Gemma-3-4B (prompt_injected): 9 rows

| item | bn_roman query | en correct? | param | gold | predicted | note |
|---|---|---|---|---|---|---|
| 196 | 2022/08/16 tarikh e London er air quality index koto chhilo? | NO | date | 08-16-2022 | "2022-08-16" |  |
| 199 | San Jose te agami tin diner batasher man kemon thakbe ber koro to. | yes | days | 3 | 7 |  |
| 203 | Chicago r batasher man ar dushoner samprotik tothogulo ki ektu khuje debe? | yes | detail | True | (missing) |  |
| 193 | Toronto te nana dhoroner ekborshojibi gach pawa jay emon shera kichu sthaniyo nursery khuje dao. | yes | plant_types | ['Annual'] | ["Annual", "Herbs"] |  |
| 369 | Houston e amar kache organic folmul ar shakshobji pawa jay emon mudi dokan kothay ache? | yes | categories | ['Organic', 'Vegetables', 'Fruits'] / ['Organic', 'Fruits', 'Vegetables'] / ['Vegetables', 'Fruits', 'Organic'] | ["Organic"] |  |
| 303 | 2019-2020 moushume Cristiano Ronaldo r performance er porishongkhan ber koro. | yes | league | (optional) | "er porishongkhan" | BANGLA-WORD? |
| 309 | 2020 shaler NFL moushume Tom Brady r record ta khuje ber koro to. | yes | player_name | Tom Brady | "Moushume" | BANGLA-WORD? |
| 309 | 2020 shaler NFL moushume Tom Brady r record ta khuje ber koro to. | yes | team | Tampa Bay Buccaneers | "Tom Brady" |  |
| 288 | New York City te Eminem er poroborti concert er duto ticket kete dao. | yes | num_tickets | 2 | 1 |  |
| 328 | 'Ticket to Ride' board game tir rating ar kotojon khelowar eksathe khelte paren ta ber koro. | NO | parameters | ['rating', 'player count'] / ['player count', 'rating'] | (missing) |  |

## Llama-3.1-8B (template): 9 rows

| item | bn_roman query | en correct? | param | gold | predicted | note |
|---|---|---|---|---|---|---|
| 199 | San Jose te agami tin diner batasher man kemon thakbe ber koro to. | yes | days | 3 | 30 |  |
| 193 | Toronto te nana dhoroner ekborshojibi gach pawa jay emon shera kichu sthaniyo nursery khuje dao. | yes | plant_types | ['Annual'] | "['Annual', 'Perennial', 'Shrub', 'Tree', 'Herbs', 'Fruits']" |  |
| 377 | Australia r Sydney te ekhon shomoy koto? | yes | format | HH:MM:SS | "%H:%M:%S" |  |
| 303 | 2019-2020 moushume Cristiano Ronaldo r performance er porishongkhan ber koro. | NO | league | (optional) | "Premier League" |  |
| 306 | gawto 10 match e cricketer Virat Kohli r batting gawrer hishabta ber koro. | yes | match_format | T20 | "Test" |  |
| 309 | 2020 shaler NFL moushume Tom Brady r record ta khuje ber koro to. | yes | team | Tampa Bay Buccaneers | "New England Patriots" |  |
| 357 | vegan chocolate cake bananor recipe dao, dhape dhape. | yes | dish_name | chocolate cake / vegan chocolate cake | "vegan chocolate cake bananor" | BANGLA-WORD? |
| 215 | 'Interstellar' cinema tar kahini shonkhepe ektu bolo to. | yes | extra_info | False | "true" |  |
| 328 | 'Ticket to Ride' board game tir rating ar kotojon khelowar eksathe khelte paren ta ber koro. | yes | parameters | ['rating', 'player count'] / ['player count', 'rating'] | "['rating', 'playing time']" |  |
| 328 | 'Ticket to Ride' board game tir rating ar kotojon khelowar eksathe khelte paren ta ber koro. | yes | language | English | "Bengali" |  |
