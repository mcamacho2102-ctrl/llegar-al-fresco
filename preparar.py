import csv,json,math,xml.etree.ElementTree as ET
from pathlib import Path
from pyproj import Transformer
from datetime import date

base=Path(__file__).parent
convert=Transformer.from_crs(25830,4326,always_xy=True)
root=ET.parse(base/'datos/osm-piloto.xml').getroot()
nodes={n.get('id'):[float(n.get('lat')),float(n.get('lon'))] for n in root.findall('node')}
ways=[]
for w in root.findall('way'):
 tags={t.get('k'):t.get('v') for t in w.findall('tag')}
 if 'highway' not in tags or tags['highway'] in ('motorway','motorway_link','trunk','trunk_link','construction','proposed','steps') or tags.get('foot') in ('no','private') or tags.get('access')=='private' or tags.get('area')=='yes':continue
 ids=[n.get('ref') for n in w.findall('nd') if n.get('ref') in nodes]
 if len(ids)>1: ways.append({'ids':ids,'name':tags.get('name','Calle sin nombre')})
used={k for w in ways for k in w['ids']}
coords={k:v for k,v in nodes.items() if k in used}
raw=json.load(open(base/'datos/bancos-original.json'))
banks=[]
for a in raw:
 try:
  lng,lat=convert.transform(float(a['COORD_GIS_X']),float(a['COORD_GIS_Y']))
  if 40.406<=lat<=40.410 and -3.714<=lng<=-3.707 and a['ESTADO']=='OPERATIVO':banks.append({'id':str(a['ID']),'lat':lat,'lon':lng,'address':' '.join(filter(None,[a.get('TIPO_VIA'),a.get('NOM_VIA'),a.get('NUM_VIA')])),'model':a.get('MODELO')})
 except (TypeError,ValueError):continue
health=[]
with open(base/'datos/centros_servicios_establecimientos_sanitarios.csv',encoding='utf-8-sig',newline='') as f:
 for row in csv.DictReader(f,delimiter=';'):
  try:lon,lat=convert.transform(float(row['localizacion_coordenada_x']),float(row['localizacion_coordenada_y']))
  except (KeyError,ValueError,TypeError):continue
  if 40.406<=lat<=40.410 and -3.714<=lon<=-3.707:
   health.append({'name':row['centro_tipo']+' · '+row['direccion_vial_nombre']+' '+row['direccion_vial_nro'],'lat':lat,'lon':lon,'type':'Sanidad','source':'Comunidad de Madrid'})
lib=[]
with open(base/'datos/spacm_listado_bibliotecas_servicios_lectura.csv',encoding='cp1252',newline='') as f:
 for row in csv.DictReader(f,delimiter=';'):
  if 'PEDRO SALINAS' in row.get('nombre_biblioteca','').upper():lib.append(row)
for w in root.findall('way'):
 tags={t.get('k'):t.get('v') for t in w.findall('tag')}
 if tags.get('name')=='Biblioteca Pública Pedro Salinas' and lib:
  points=[nodes[t.get('ref')] for t in w.findall('nd') if t.get('ref') in nodes]
  health.insert(0,{'name':'Biblioteca Pública Pedro Salinas','lat':sum(v[0] for v in points)/len(points),'lon':sum(v[1] for v in points)/len(points),'type':'Biblioteca','source':'Comunidad de Madrid + OpenStreetMap','hours':lib[0].get('horario','')})
result={'nodes':coords,'ways':ways,'banks':banks,'destinations':health,'bounds':[[40.406,-3.714],[40.410,-3.707]],'sources':{'banks':'Ayuntamiento de Madrid, inventario 2026','roads':'OpenStreetMap, descarga 19/11/2026','destinations':'Comunidad de Madrid, descarga 19/11/2026'}}
(base/'dist/data.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')))
print('nodos',len(coords),'vías',len(ways),'bancos',len(banks),'destinos',len(health))
for h in health[:10]:print(h['name'],h['lat'],h['lon'])
