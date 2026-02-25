# Introduction
Les algoithmes de tracé de rayon sont omnirpésents dans les moteur de rendu de pointe. Les traceurs de chemin de Monte Carlo ont été utilisés pour rendre des maillages, tandis que les volumes sont rendus à l’aide du path tracing volumétrique. Certains media se situent entre les représentations volumétriques et surfaciques, comme les cheveux et la fourrure.

Un nouveau paradigme prometteur a récemment été présenté par seyb et al dans  _From Microfacets to Participating Media: A Unified Theory of Light Transport with Stochastic Geometry_. Ils proposent un nouvel algorithme de tracé de rayon pour faire le rendu de surface implicite défini par processus de gauss (GPIS), ouvrant ainsi la voie à un continuum d'élément d'une scène pouvant être rendu avec le même algorithme. 

Cette recherche vise à déterminer si le rendu des cheveux peut être réalisé efficacement à l’aide de ce nouveau continuum. Ce rapport d’avancement partiel présente les résultats et l’orientation du projet de recherche, ainsi que les progrès réalisés sur la preuve de concept de représentation de GPIS pour Mitsuba 3.

La section de revue de littérature présente les éléments théoriques importants liés à la difficulté d’utiliser plusieurs algorithmes de rendu pour une même scène, ainsi que l’état de l’art en matière de rendu des cheveux et de la fourrure. Elle introduit également les notions essentielles de processus gaussiens et de GPIS.

Les GPIS ne sont pas nouveaux, mais leur utilisation pour le rendu de scènes est relativement récente et n’a été démontrée jusqu’à présent que par l’équipe de Seyb et al. Il serait particulièrement intéressant d’implémenter l’algorithme proposé dans le moteur de rendu largement utilisé Mitsuba 3. Dans ce rapport d’avancement partiel, je présenterai le processus de décision ayant mené au choix du moteur de rendu ainsi que l’état actuel de la preuve de concept.

Enfin, je présenterai la manière dont l’implémentation GPIS sera compparer à l’approche de référence basée sur le Tracé de rayon Monte Carlo.

# Littérature

## Représentation d'une scène
La représentation de scène en rendu fait référence à la manière dont les environnements 3D et leurs éléments constitutifs sont organisés, stockés et décrits pour être utilisés dans les pipelines de rendu. Les formats modernes de description de scène, tels que Universal Scene Description (USD) et glTF (GL Transmission Format), constituent la base de cette organisation.

USD, développé par Pixar, est conçu pour l’interopérabilité entre différents logiciels 3D, en mettant l’accent sur des descriptions de scène éditables destinées aux outils de création numérique. De son côté, glTF est optimisé pour la diffusion de contenu et le rendu final, notamment pour le web et les applications en temps réel. Ces formats encodent différents types d’actifs, notamment des maillage d'objet, des personnages dotés de systèmes squelettiques et de cheveux, ainsi que des média participatifs comme la fumée, le brouillard ou la vapeur.

### Diversité des pipelines de rendu

Différents types de élément de la scène nécessitent des approches de rendu spécialisées. Par exemple, Blender Cycles utilise un path tracer volumétrique pour rendre les milieux participatifs, tout en employant le lancer de rayons standard pour les mailles d'objets. Cette séparation reflète les différences fondamentales entre l’interaction de la lumière avec les surfaces et avec les volumes.

### 2.1.2 Formats d’encodage des actifs

Le paysage des formats d’encodage des actifs est très fragmenté, chaque type d’actif nécessitant sa propre représentation spécialisée :

**Mailles**  
Les mailles de géométrie utilises généralement des approches similaires au format Wavefront OBJ, qui encode les positions des sommets, les normales, les coordonnées de texture ainsi que les indices de sommets définissant la topologie des faces triangulaires ou polygonales.

**Milieux participants (Participating Media)**  
Les données volumétriques telles que la fumée, le brouillard, le feu ou les nuages sont couramment stockées à l’aide de formats comme OpenVDB, une bibliothèque open source initialement développée par DreamWorks Animation pour manipuler des données volumétriques creuses (sparse). OpenVDB permet un stockage efficace de structures voxelisées pour la fumée, le feu et les simulations de fluides grâce à une structure hiérarchique clairsemée qui ne conserve que les régions occupées, réduisant drastiquement les besoins mémoire comparativement aux grilles volumétriques denses.

**Cheveux et fourrure basés sur des brins (Strand-Based Hair and Fur)**  
Les cheveux et la fourrure posent des défis d’encodage particuliers. Les mèches sont généralement représentées sous forme de courbes, souvent à l’aide de splines cubiques de Catmull-Rom ou de courbes de Bézier, définies par des points de contrôle décrivant la trajectoire du brin. Ces représentations incluent des informations de largeur par sommet le long de la spline afin de capturer l’amincissement progressif du cheveu de la racine vers la pointe. L’encodage doit donc stocker non seulement la courbe centrale, mais également les paramètres de largeur permettant au moteur de rendu de reconstruire correctement la nature volumétrique du cheveu lors du rendu.

### 2.1.3 Le défi de la fragmentation

Cette diversité de formats de représentation implique que les pipelines de rendu doivent prendre en charge plusieurs types d’actifs, chacun possédant des structures mémoire, des routines d’intersection et des modèles d’ombrage distincts.

Une approche unifiée capable de tout traiter des surfaces au volumes avec une représentation unique pourrait simplifier considérablement les architectures de rendu. Cela constitue une partie de la motivation derrière l’exploration de techniques telles que les GPIS.

## 2.2 Cheveux

### 2.2.1 État de l’art du rendu des cheveux

Les cheveux et la fourrure sont omniprésents dans les médias rendus, des jeux vidéo aux personnages de films d’animation. Encore aujourd’hui, le rendu réaliste des fibres demeure un défi, tant en raison de leur complexité géométrique que de la diffusion lumineuse complexe d’une fibre à l’autre.

La plupart des techniques modernes trouvent leur origine soit dans l’approche des _carte de cheveux_ proposée par James T. Kajiya et Timothy L. Kay, soit dans le paradigme de diffusion par fibres introduit par Stephen R. Marschner et al.

Recement, la recherche se concentre sur la formulation de modèles de diffusion compatibles avec les traceurs de rayon Monte Carlo. Par exemple, Chiang et al. ont développé un modèle pratique pour les artistes, aujourd’hui largement adopté comme modèle de nuançage des cheveux dans des outils tels que Houdini et Mitsuba 3.

### Modèle de Kajiya et Kay

Le modèle de Kajiya et Kay (1989) repose sur une représentation polygonale des cheveux, ce qui lui permet de s’intégrer facilement aux pipelines de rendu par Rastérisation. L’approche consiste à modéliser les cheveux comme des fibres cylindriques et à utiliser un modèle d’ombrage anisotrope tenant compte de la direction tangente du brin.

Le modèle capture la caractéristique la plus visible de la diffusion par les fibres : l’apparition d’un reflet linéaire perpendiculaire à la direction des fibres dans l’image. Cette propriété repose sur l’observation qu’une réflexion d’un faisceau parallèle sur la surface d’un cylindre produit un cône centré sur l’axe du cheveu. Le modèle combine un terme diffus (proportionnel au cosinus de l’angle d’incidence) avec un reflet spéculaire centré sur ce cône.

Cependant, le modèle de Kajiya et Kay présente des limites importantes. Il traite les cheveux comme des cylindres opaques et ne tient pas compte de la transmission ni des réflexions internes. Or, le cheveu étant un matériau diélectrique et translucide conduit à un rendu moins réaliste, incapable de reproduire correctement les reflets colorés et les effets de rétroéclairage observés dans les cheveux réels.

### Modèle de Marschner

Le modèle de Marschner (2003) constitue une avancée majeure par rapport à celui de Kajiya et Kay en proposant une modélisation basé sur des observation clinique des fibres de cheveux. Les cheveux y sont représentées comme des cylindres diélectriques rugueux, permettant de simuler correctement la réflexion interne et la transmission.

Marschner identifie trois principaux modes d’interaction de la lumière avec un cheveu :

- **R (Reflection)** : la lumière se réfléchit sur la surface externe de la fibre, produisant le reflet blanc principal.
    
- **TT (Transmission-Transmission)** : la lumière pénètre dans la fibre, traverse son intérieur et ressort de l’autre côté, produisant une diffusion vers l’avant visible en situation de contre-jour.
    
- **TRT (Transmission-Reflection-Transmission)** : la lumière pénètre dans la fibre, se réfléchit sur la surface interne opposée, puis ressort, générant le reflet secondaire coloré.
    

La fonction de diffusion peut s’écrire :

S(θi,θr,ϕi,ϕr)=MR(θh)NR(η′(η,θd),ϕ)cos⁡2(θd)+MTT(θh)NTT(η′(η,θd),ϕ)cos⁡2(θd)+MTRT(θh)NTRT(η∗(ϕh,θd),ϕ)cos⁡2(θd)S(\theta_i, \theta_r, \phi_i, \phi_r) = \frac{M_R(\theta_h) N_R(\eta'(\eta, \theta_d), \phi)}{\cos^2(\theta_d)} + \frac{M_{TT}(\theta_h) N_{TT}(\eta'(\eta, \theta_d), \phi)}{\cos^2(\theta_d)} + \frac{M_{TRT}(\theta_h) N_{TRT}(\eta^*(\phi_h, \theta_d), \phi)}{\cos^2(\theta_d)}S(θi​,θr​,ϕi​,ϕr​)=cos2(θd​)MR​(θh​)NR​(η′(η,θd​),ϕ)​+cos2(θd​)MTT​(θh​)NTT​(η′(η,θd​),ϕ)​+cos2(θd​)MTRT​(θh​)NTRT​(η∗(ϕh​,θd​),ϕ)​

où :

- **M** représente la fonction de diffusion longitudinale (modélisée par des gaussiennes),
    
- **N** représente la fonction de diffusion azimutale.

En principe, ce schéma pourrait être répété à l'infini en considérant des transmissions comportant un nombre arbitraire de réflexions internes (par exemple TRRT, TRRRT, etc.). Toutefois, l’impact visuel des termes d’ordre supérieur au TRT est généralement négligeable.


### 2.2.2 Comparaison des modèles de rendu des cheveux

La figure 1 illustre, à gauche, des cheveux rendus avec le modèle de Kajiya-Kay, au centre avec le modèle de Marschner, et à droite des cheveux réels sous des conditions d’éclairage similaires.

On observe clairement que le modèle de Marschner permet une meilleure reproduction des reflets secondaires colorés et offre un aspect moins plat que le modèle de Kajiya-Kay. Néanmoins, il conserve une certaine uniformité et ne capture pas encore parfaitement la richesse visuelle des cheveux réels.

_Figure 1 : Comparaison des modèles de rendu des cheveux : modèle de Kajiya-Kay (gauche), modèle de Marschner (centre) et cheveux réels (droite) sous un éclairage similaire. Image tirée de Marschner et al. [3]._


## 2.3 Processus gaussiens

Les processus gaussiens (GP) constituent un cadricielle d’apprentissage automatique qui considère l’ensemble des fonctions possibles pouvant approximer un jeu de données, en assignant une probabilité à chacune d’elles.

L’hypothèse clé sous-jacente aux GP est que des points d’entrée similaires doivent produire des sorties similaires. Cela permet au modèle de fournir, pour chaque prédiction, non seulement une estimation de la valeur attendue, mais aussi un degré d’incertitude associé, sous forme de variance.

Les GP sont définis par deux fonctions :

1. **La fonction moyenne** µ(x), qui représente les croyances a priori sur la fonction sous-jacente.
    
2. **Le noyau de covariance** k(x, x′), qui représente la corrélation entre deux points.
    

Les GP effectuent leurs prédictions en fournissant :

- une moyenne de la distribution postérieur correspondant à la valeur prédite,
    
- une variance de la distribution postérieur représentant l’incertitude associée à cette prédiction.
    

---

### 2.3.1 Noyaux

La fonction noyau est utilisée pour définir la matrice de covariance en encodant la corrélation entre deux points. Le choix du noyau est crucial en modélisation par GP, car il incorpore des hypothèses sur la régularité, la périodicité et d’autres propriétés de la fonction sous-jacente

#### Noyau exponentiel quadratique (RBF)

Le noyau exponentiel quadratique (ou noyau RBF) est défini par :

kSE(x,x′)=σ2exp⁡(−12ℓ2∥x−x′∥2)k_{SE}(x, x') = \sigma^2 \exp \left(- \frac{1}{2\ell^2} \|x - x'\|^2 \right)kSE​(x,x′)=σ2exp(−2ℓ21​∥x−x′∥2)

où :

- σ2\sigma^2σ2 est la variance du signal,
    
- ℓ\ellℓ est le paramètre d’échelle (longueur caractéristique).
    

Ce noyau est particulièrement pertinent pour les GPIS, car il produit des surfaces infiniment différentiables et donc très lisses. Le paramètre d’échelle ℓ\ellℓ offre un contrôle intuitif sur les caractéristiques de la surface : des valeurs faibles produisent des variations rapides entre les points, tandis que des valeurs plus grandes imposent des transitions plus douces. Cette interprétabilité et cette flexibilité en font un choix adapté à la représentation d’objets naturels aux frontières continues et régulières.

Les équations des noyaux sont tirées de Martens et al.

#### Noyau Thin Plate Spline

Dans le cas tridimensionnel, le noyau _thin plate spline_ est donné par :

kTP(x,x′)=2d3−3Rd2+R3k_{TP}(x, x') = 2d^3 - 3R d^2 + R^3kTP​(x,x′)=2d3−3Rd2+R3

où :

- d=∥x−x′∥2d = \|x - x'\|^2d=∥x−x′∥2,
    
- RRR est un hyperparamètre définissant le rayon de support.
    

Ce noyau est motivé par la minimisation de l’énergie de flexion, analogue à la déformation d’une plaque mince physique. Pour les GPIS, cette propriété est avantageuse, car elle génère naturellement des surfaces à courbure minimale, produisant des interpolations lisses entre des points de données clairsemés. Toutefois, contrairement au noyau exponentiel quadratique, son efficacité est limitée à un domaine fini défini par RRR, et il offre moins de flexibilité pour ajuster les propriétés de la surface.

---

### 2.3.2 Conditionnement

Le conditionnement d’un processus gaussien consiste à incorporer des données observées afin d’affiner les prédictions en générant un distribution postérieur. Les équations de conditionnement et d’échantillonnage sont dérivées dans Martens et al. ainsi que dans _From Microfacets to Participating Media: A Unified Theory of Light Transport with Stochastic Geometry_. Nous adoptons ici la notation de Seyb et al., plus explicite.

Étant donné des mesures **m** aux positions **C**, le processus gaussien conditionné a posteriori est :

f∼GP(μ∣ζm(x),k∣ζm(x,y))f \sim GP(\mu_{|\zeta_m}(x), k_{|\zeta_m}(x,y))f∼GP(μ∣ζm​​(x),k∣ζm​​(x,y))

avec :

μ∣ζm(x)=μ(x)+k(x,C)k(C,C)−1(m−μ(C))\mu_{|\zeta_m}(x) = \mu(x) + k(x,C) k(C,C)^{-1} (m - \mu(C))μ∣ζm​​(x)=μ(x)+k(x,C)k(C,C)−1(m−μ(C)) k∣ζm(x,y)=k(x,y)−k(x,C)k(C,C)−1k(C,y)k_{|\zeta_m}(x,y) = k(x,y) - k(x,C) k(C,C)^{-1} k(C,y)k∣ζm​​(x,y)=k(x,y)−k(x,C)k(C,C)−1k(C,y)

---

### 2.3.3 Échantillonnage corrélé

L’échantillonnage d’un processus gaussien peut être réalisé directement via :

f(X)=μ(X)+k(X,X)1/2ηf(X) = \mu(X) + k(X,X)^{1/2} \etaf(X)=μ(X)+k(X,X)1/2η

où :

- η∼N(0,1)\eta \sim \mathcal{N}(0,1)η∼N(0,1)
    
- A1/2A^{1/2}A1/2 est la racine carrée matricielle telle que A=A1/2A1/2A = A^{1/2} A^{1/2}A=A1/2A1/2
    

Cette formulation permet de générer des réalisations de fonctions compatibles avec la moyenne et la covariance spécifiées par le GP.

## 2.4 Surfaces implicites

Une surface implicite est définie par une fonction ( f(X) ), où la surface correspond à l’ensemble des points tels que ( f = 0 ). Par convention, les points où ( f > 0 ) sont considérés comme étant à l’intérieur de l’objet et ceux où ( f < 0 ) à l’extérieur, bien que cette convention puisse être inversée.

Cette représentation est populaire, car les surfaces implicites sont lisses, peuvent être correctement contraintes par une géométrie connue et ne nécessitent aucun traitement particulier lors des changements de topologie.

---

### 2.4.1 Surfaces implicites par processus gaussien (GPIS)

Les surfaces implicites définies par processus gaussien (GPIS) ont été introduites par Christopher K. I. Williams et Andrew Fitzgibbon comme une approche probabiliste de reconstruction de surface .

La moyenne du processus gaussien décrit une variété représentant l’actif géométrique.

Les données d’entraînement d’un GPIS comprennent :

- Un ensemble de points situés sur la surface (où ( f = 0 ))
    
- Un ensemble de points connus à l’intérieur de la surface (où ( f > 0 ))
    
- Un ensemble de points connus à l’extérieur de la surface (où ( f < 0 ))
    

Si des points sont associés à des vecteurs normaux, il est possible de générer automatiquement des points intérieurs et extérieurs en se déplaçant légèrement dans le sens et dans le sens opposé à la normale.

Le processus gaussien apprend une fonction qui interpole de manière lisse tous les points observés. La moyenne du GP représente la fonction implicite la plus probable, tandis que la variance fournit une estimation de l’incertitude. La surface implicite correspond à l’ensemble des points tels que ( f(X) = 0 ).

#### Noyau de covariance Thin Plate

Williams et Fitzgibbon ont dérivé un noyau de covariance équivalent au régularisateur _thin plate spline_. Pour des surfaces tridimensionnelles, le noyau s’écrit :

[  
k_{tp}(x, x') = 2d^3 - 3R d^2 + R^3  
]

où :

- ( d = |x - x'| ) est la distance entre les points,
    
- ( R ) est un hyperparamètre.
    

Ce noyau est semi-défini positif et symétrique, garantissant que la matrice de covariance est valide pour l’inférence par processus gaussien.

Le noyau _thin plate_ favorise la régularité en pénalisant l’énergie de flexion de la surface, mesurée par l’intégrale des dérivées secondes au carré. Cette propriété le rend particulièrement adapté aux tâches de reconstruction de surface [6].

---

### 2.4.2 Représentation d’actifs à l’aide de processus gaussiens

Les GPIS sont particulièrement intéressants pour représenter des formes issues de scans LiDAR ou de caméras RGB-D. À partir d’un nuage de points, on peut conditionner le processus gaussien en fixant les points du nuage comme observations (avec ( f = 0 )). Cela définit une variété pouvant être rendue à l’aide d’algorithmes de _ray marching_, en recherchant les racines pour déterminer l’intersection avec la variété définie par ( f(X) = 0 ).

Pour des actifs basés sur des maillages, le GP peut être conditionné en :

1. Ajoutant chaque sommet du maillage comme observation de surface (( f = 0 ))
    
2. Utilisant les normales aux sommets pour ajouter des points extérieurs (( f = -1 )) et intérieurs (( f = +1 )) en les décalant le long de la direction normale
    

La figure 2 illustre le lapin de Stanford défini par 800 points de surface, un point intérieur de valeur +1 et une sphère de 80 points extérieurs de valeur −1 générés par l’algorithme des _marching cubes_. Image tirée de Williams et Fitzgibbon [7].

Pour les nuages de points issus de scans LiDAR, les normales ainsi que les points intérieurs et extérieurs doivent être estimés à partir de la géométrie locale. Cela peut être réalisé en estimant les normales de surface à partir du gradient du processus gaussien [6].

Le GP conditionné résultant définit une surface implicite interpolant lisse­ment les données observées tout en fournissant des estimations d’incertitude loin des observations. Cette représentation probabiliste est particulièrement utile pour traiter des données capteurs bruitées et des observations clairsemées.

---

### 2.4.3 Dérivées des processus gaussiens et normales de surface

Une propriété essentielle des processus gaussiens est que leurs dérivées sont également des processus gaussiens. Cette propriété est fondamentale pour les GPIS, car les normales de surface sont obtenues à partir du gradient de la fonction implicite.

#### Processus gaussiens dérivés

En raison de la linéarité de l’opérateur de dérivation, la dérivée d’un processus gaussien s’écrit :

[  
GP'(\mu(x), k(x,y)) = GP(\mu'(x), k_{xy}(x,y))  
]

où :

[  
k_{xy}(x,y) = \frac{\partial^2 k(x,y)}{\partial x \partial y}  
]

Ainsi, la covariance entre dérivées peut être calculée en prenant la dérivée croisée d’ordre deux du noyau original.

#### Calcul des normales sur une GPIS

Pour une surface implicite définie par ( f(X) = 0 ), la normale en un point est donnée par le gradient normalisé :

[  
n(x) = \frac{\nabla f(x)}{|\nabla f(x)|}  
]

---

## 2.5 Une théorie unifiée du transport de la lumière par géométrie stochastique

Dans _From Microfacets to Participating Media: A Unified Theory of Light Transport with Stochastic Geometry_ [1], Seyb et al. utilisent les GPIS pour définir un modèle contrôlable capable de représenter tous les éléments d’une scène comme un continuum. Cela permet une représentation de scène reposant sur un modèle unique de transport de la lumière.

---

### 2.5.1 Algorithme

L’algorithme de path tracing pour les GPIS utilise la fonction classique **nextHit** pour déterminer les intersections rayon-surface. Cette fonction calcule la première distance ( t ) telle que le rayon ( x + t w ) intersecte la surface définie par ( f(x_t) = 0 ).

Pour trouver cette intersection, on génère une réalisation unidimensionnelle du processus gaussien le long du rayon, puis on recherche un changement de signe de cette fonction 1D. On échantillonne le processus gaussien en ( n ) points le long du rayon, puis on interpole entre ces points afin de créer une réalisation continue adaptée à une recherche de racine permettant de localiser le passage par zéro.

Une fois le point d’intersection obtenu, on utilise la méthode du gradient décrite précédemment pour calculer la normale de surface. Avec le point d’intersection et le vecteur normal, il est alors possible d’évaluer la BSDF exactement comme dans un algorithme de tracé de rayon standard.

## 3 Implémentation

### 3.1 Choix d’un moteur de rendu

Comme discuté précédemment, pour rendre une GPIS à l’aide du transport de la lumière, il est nécessaire d’échantillonner les intersections rayon-surface à partir d’un processus gaussien conditionné et de retourner des interactions de surface comme dans un algorithme classique de transport de la lumière.

Une implémentation complète à partir de zéro pourrait être réalisée en utilisant CUDA ou des _compute shaders_ OpenGL. Cela impliquerait de définir la traversée de scène, les routines d’intersection de rayons, l’échantillonnage par importance multiple, les interactions de surface, ainsi que l’analyse de scène et le transfert des données du CPU vers la mémoire GPU. Cette approche offrirait un contrôle total sur le moteur de rendu, mais nécessiterait également l’implémentation d’une quantité importante d’infrastructure de lancer de rayons sans lien direct avec les GPIS.

Une alternative consisterait à créer un nœud personnalisé pour un moteur de rendu de pointe tel que Blender Cycles ou Autodesk Arnold. Ces deux moteurs utilisent le path tracing Monte Carlo pour les milieux volumiques et les maillages, et permettent la création de plugins ou de nœuds personnalisés. Toutefois, ils ne fournissent pas suffisamment de flexibilité pour définir un comportement d’intersection basé sur l’échantillonnage d’un processus gaussien, ce qui est essentiel pour l’intégration des GPIS.

Une troisième option consiste à utiliser un moteur orienté recherche. Tungsten est le moteur utilisé par Seyb et al. [1] et Xu et al. [11]. Développé par Benedikt Bitterli [10], il inclut une implémentation GPIS disponible sur GitHub. Bien que public, ce moteur n’est pas conçu pour une utilisation générale et manque de documentation. La version publiée ne supporte pas le chargement de fichiers de cheveux ni le conditionnement du processus gaussien à partir de splines extraites. Ajouter cette fonctionnalité serait intéressant, mais nécessiterait une rétro-ingénierie importante du code existant.

Mitsuba 3 [12] constitue une option populaire pour la recherche en rendu. Il s’agit d’un moteur retargetable développé par Wenzel Jakob et son équipe à l’EPFL. Il expose une API Python permettant de définir des plugins personnalisés tels que des intégrateurs ou des BSDF. Bien que l’API Python ne permette pas de définir des routines d’intersection personnalisées, cela est possible via l’implémentation d’une forme personnalisée dans le code C++17.

Étant un projet open source orienté recherche, Mitsuba 3 représente un bon compromis. Comparé à une implémentation complète à partir de zéro, il permet de gagner du temps en réutilisant les routines de lancer de rayons existantes. Contrairement à Tungsten, il est activement maintenu et documenté. Enfin, il offre une flexibilité significative tout en supportant l’exécution retargetable, contrairement à Cycles et Arnold.

---

### 3.2 Mitsuba 3

D’après la page GitHub officielle :

Mitsuba 3 est un système de rendu orienté recherche pour la simulation du transport de la lumière direct et inverse, développé à l’EPFL en Suisse. Il comprend une bibliothèque cœur ainsi qu’un ensemble de plugins implémentant des fonctionnalités allant des matériaux et sources lumineuses aux algorithmes complets de rendu. Mitsuba 3 est retargetable, ce qui signifie que ses implémentations et structures de données peuvent être transformées pour accomplir différentes tâches [12].

---

### 3.2.1 L’API

Les éléments suivants sont tirés de la documentation officielle de Mitsuba 3 [12].

#### Plugins

L’architecture de path tracing de Mitsuba est divisée en composants appelés plugins, représentant les systèmes nécessaires au rendu.

#### Intégrateur

Les intégrateurs définissent la manière de résoudre l’équation du transport de la lumière. Ils gèrent la traversée de la scène et déterminent la stratégie de rendu. La plupart définissent un paramètre de profondeur contrôlant le nombre de rebonds du rayon. L’intégrateur _path tracer_ existant constitue un bon point de départ, car il implémente déjà l’échantillonnage par importance multiple et d’autres optimisations utiles.

#### Formes (Shapes)

Les formes définissent les surfaces marquant la transition entre différents milieux, comme l’interface entre l’air et un solide. Elles doivent définir une boîte englobante utilisée lors de la traversée de scène.

Mitsuba inclut des primitives de base telles que cube, sphère, plan et disque, ainsi que des formes maillées chargeant des fichiers Wavefront (.obj) et PLY.

Ce projet nécessite la création d’une forme personnalisée nommée **gpis_shape**, capable de charger des sommets et de conditionner un processus gaussien. L’API Shape implémente la routine d’intersection appelée par l’intégrateur, laquelle retourne un objet d’interaction de surface décrivant le comportement lumineux après franchissement de la boîte englobante.

#### BSDF

Les BSDF modélisent la diffusion de la lumière sur une surface. Une BSDF personnalisée ne devrait pas être nécessaire, puisque la diffusion d’une GPIS doit se comporter comme celle d’un maillage équivalent. La forme gpis_shape doit donc être compatible avec toute BSDF existante. Une BSDF capillaire implémentant le modèle de Chiang et al. [4] est déjà disponible.

#### Échantillonneur

Les échantillonneurs génèrent les nombres aléatoires utilisés pour l’intégration Monte Carlo.

---

### 3.3 Preuve de concept

Une preuve de concept a été réalisée en ajoutant un plugin **gpis_sphere** à Mitsuba 3. La forme conditionne un processus gaussien à partir de 201 observations : 100 points de surface, 100 points extérieurs et un point intérieur.

L’intersection est définie à partir de la moyenne du processus gaussien conditionné. La sphère est placée dans une scène de type Cornell Box via la description XML de Mitsuba, avec des murs définis par des rectangles et un éclairage fourni par une source surfacique.

La scène est rendue en 256 × 256 pixels avec 128 échantillons par pixel, pour un temps de rendu d’environ 30 minutes.

---

### 3.4 Défis de développement

#### 3.4.1 Configuration de l’environnement

La compilation de Mitsuba 3 a nécessité une configuration précise des dépendances. Plutôt que de modifier directement le dépôt principal, Mitsuba 3 a été lié comme bibliothèque externe au plugin via CMake, ce qui a exigé une compréhension détaillée de la chaîne de compilation.

#### 3.4.2 Développement de la bibliothèque GP

Plusieurs itérations ont été nécessaires pour implémenter la bibliothèque de processus gaussien. La bibliothèque libgp ne permettait pas l’échantillonnage requis. Une tentative avec Eigen3 a entraîné des conflits de types avec DrJit.

DrJit est le compilateur JIT utilisé par Mitsuba 3, permettant la compilation vers CUDA, LLVM ou un backend scalaire à partir d’un code unifié. Cependant, le traitement SIMD de la routine d’intersection entrait en conflit avec les types standards C++ et Eigen3. La solution a consisté à implémenter entièrement la classe de processus gaussien en syntaxe DrJit.

Actuellement, gaussian_process.h permet de conditionner un modèle à partir d’observations de surface, extérieures et intérieures avec un noyau RBF. L’intersection repose encore sur un _ray marching_ vers la moyenne du processus, sans échantillonnage corrélé.

---

### 3.5 Résultats et analyse

La scène Cornell Box avec sphère GPIS montre plusieurs caractéristiques :

- La surface présente des irrégularités dues au conditionnement clairsemé de 100 points.
    
- L’éclairage confirme la compatibilité avec le système BSDF de Mitsuba 3.
    
- Les normales utilisent encore celles d’une sphère analytique plutôt que le gradient réel, ce qui cause des artefacts triangulaires noirs.
    
- Une légère transparence apparaît au sommet, illustrant le caractère stochastique des GPIS et leur capacité à représenter un continuum entre surfaces solides et milieux participants.
    

---

### 3.6 Prochaines étapes

La prochaine phase se concentrera sur :

1. L’implémentation de l’échantillonnage corrélé du processus conditionné.
    
2. L’ajout du calcul des normales basé sur le gradient.
    

Ces améliorations permettront de reproduire fidèlement l’approche décrite par Seyb et al. [1].

Ensuite, le système sera étendu au rendu de maillages en conditionnant le processus à partir de sommets importés depuis des fichiers OBJ. L’augmentation du nombre d’observations ralentira le rendu, rendant pertinente l’approche matricielle creuse proposée par Xu et al. [11].

Enfin, il faudra déterminer quel noyau est adapté au rendu des cheveux afin d’éviter la fusion indésirable des mèches. Cette question constitue un problème nouveau encore peu exploré dans la littérature sur les GPIS et le rendu capillaire.



## 4 Évaluation

### 4.1 Méthodologie

Nous évaluerons l’implémentation de GPIS à l’aide de deux métriques principales : la qualité d’image et les performances de rendu.

### 4.1.1 Évaluation de la qualité d’image

Nous utiliserons l’erreur quadratique moyenne (Mean Squared Error, MSE) pour comparer les images rendues avec un path tracer classique à celles rendues avec l’objet GPIS. La MSE fournit une mesure quantitative pixel par pixel de la différence entre deux images, ce qui la rend appropriée pour évaluer si l’approche GPIS produit des résultats visuellement équivalents au rendu traditionnel basé sur des maillages.

La MSE est calculée comme suit :

[  
MSE = \frac{1}{N} \sum (I_{reference} - I_{gpis})^2  
]

où ( N ) est le nombre total de pixels, ( I_{reference} ) représente les valeurs des pixels issues du path tracer standard et ( I_{gpis} ) représente les valeurs des pixels issues du moteur de rendu GPIS.

La MSE est une métrique pertinente pour cette évaluation car :

- Elle fournit une mesure objective et quantitative de la similarité entre les images
    
- Elle est largement utilisée en recherche en rendu pour comparer des images de référence
    
- Des valeurs plus faibles de MSE correspondent directement à des correspondances visuelles plus proches
    

### 4.1.2 Performances de rendu

Nous comparerons les temps de rendu entre l’approche traditionnelle basée sur des maillages et l’approche GPIS à trois taux d’échantillonnage différents : 8 échantillons par pixel (spp), 32 spp et 128 spp. Cela nous permettra de quantifier le surcoût de performance de l’approche GPIS par rapport au lancer de rayons standard.

En raison du coût computationnel supplémentaire lié à l’évaluation des processus gaussiens et à l’échantillonnage corrélé, j’anticipe que l’approche GPIS sera 5 à 10 fois plus lente que le rendu traditionnel basé sur des maillages.

---

## Discussion

Ce projet s’est avéré considérablement plus complexe que prévu initialement, présentant des obstacles tant sur le plan de la compréhension théorique que de la méthodologie de recherche et de l’implémentation technique.

La lecture et la compréhension des articles fondamentaux ont posé d’importants défis. La théorie des processus stochastiques nécessaire à la compréhension de GPIS dépasse mon bagage mathématique actuel, ce qui m’a obligé à revenir sur des concepts fondamentaux avant d’aborder le matériel avancé. Comme il s’agit de ma première expérience en recherche formelle, j’ai d’abord éprouvé des difficultés à adopter des stratégies efficaces d’analyse d’articles scientifiques. À travers l’expérimentation, j’ai adopté une stratégie en deux passes : d’abord une lecture initiale sans prise de notes pour saisir la structure et l’argument général ; ensuite une seconde lecture détaillée où je condense chaque paragraphe en une phrase, en utilisant Obsidian pour organiser mes notes.

Le développement de la preuve de concept pour Mitsuba 3 a présenté d’importants défis techniques. L’environnement de compilation s’est révélé particulièrement complexe, nécessitant une correspondance précise des versions de GCC, CMake, Ninja et Embree. De plus, la documentation limitée de l’interface C++ de Mitsuba 3 a exigé une rétro-ingénierie des fonctionnalités des plugins par inspection du code. Enfin, la maîtrise de la syntaxe DrJit utilisée dans l’ensemble du moteur Mitsuba 3 a ajouté un niveau supplémentaire de complexité au processus d’implémentation.

Malgré ces difficultés, ce projet de recherche a été intellectuellement stimulant et professionnellement enrichissant. J’ai acquis une exposition précieuse aux orientations de pointe en recherche en infographie, notamment l’intégration de techniques d’apprentissage automatique pour faire progresser à la fois le photoréalisme et les applications pratiques. Le projet m’a amené à revisiter des concepts fondamentaux des algorithmes de path tracing et des fonctions de diffusion de la lumière, ce qui a renforcé ma compréhension des sujets avancés au cœur de ce travail. Plus important encore, cette expérience a développé ma capacité à aborder des concepts théoriques complexes et à les appliquer à des bases de code de production existantes, une compétence essentielle en recherche et développement en infographie.

Bien que ce projet ait été plus exigeant que prévu, j’anticipe des résultats significatifs de l’intégration de GPIS dans Mitsuba 3. Une part importante de la théorie reste à explorer afin d’accroître la rigueur de la revue de littérature, notamment le modèle de mémoire utilisé pour le transport de la lumière dans [1] ainsi que l’approche plus récente de convolution creuse proposée par Xu et al. [11]. Ces ajouts fourniront une base théorique plus complète pour le travail d’implémentation à venir.