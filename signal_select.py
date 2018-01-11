# -*- encoding: utf-8 -*-
'''

      


'''
from collections import OrderedDict, defaultdict
import networkx as nx
from shapely.geometry import shape
import fiona
from operator import itemgetter


def get_signal_list():
    '''
    获得signal list
    '''
    c = fiona.open('./shp/origin_signal_clean.shp')    
    signal_list = []
    for rec in c:        
        id = int(rec['properties']['id'])
        signal_list.append(id)        
    c.close()
    
    return signal_list

def get_pnt_geom():
    '''
    读取信号灯shp文件，返回信号灯id列表和信号灯几何信息
    '''
    c = fiona.open('./shp/shenzhen_point.shp')    
    pnt_id_to_geom = {}
    for rec in c:        
        id = int(rec['properties']['ID'])
        pnt_id_to_geom[id] = rec['geometry']
        
    c.close()
    
    return pnt_id_to_geom

def get_min_out(select_signal_out_pnt_dict):
    '''
    遍历每个signal对应的out point，找出距离最近的out point
    返回对应的signal和out point
    '''
    min_out_pnt = None
    min_signal = None
    min_distance = 99999999

    for signal, out_pnt in select_signal_out_pnt_dict.items():

        if out_pnt['distance'] < min_distance:            
            min_out_pnt = out_pnt
            min_signal = signal
            min_distance = out_pnt['distance'] 

    return min_signal, min_out_pnt

def get_road_graph():
    '''
    读入路网数据构建网络结构，将所有道路看做双向的。

    '''

    road_graph = nx.Graph()  # 路网
    c = fiona.open('./shp/shenzhen_road.shp')
    
    for record in c:

        geometry = record['geometry']
        assert(geometry['type'] == 'LineString')

        properties = record['properties']
                
        length = properties['LENGTH']                
        source = properties['SOURCE']
        target = properties['TARGET']
        
        
        if length < 0:
            length = properties['REVERSE_CO']

        assert(length > 0)          

        road_graph.add_edge(source, target, **{
            'weight': length            
        })

    c.close()
    return road_graph

def write_result(travel_signal_list, signal_id_to_geom):
    driver = 'ESRI Shapefile'
    crs = {'init': 'epsg:32649'}
    schema = {
        'properties': OrderedDict([('id', 'int')]),
        'geometry': 'Point'
    }
    target_c = fiona.open('./shp/signal_v3.shp', 'w', driver=driver, crs=crs, schema=schema, encoding='utf-8')
    for signal in travel_signal_list:
        rec = {
            'type': 'Feature',
            'id': '-1',
            'geometry': signal_id_to_geom[signal],
            'properties': OrderedDict([('id', signal)])
        }
        target_c.write(rec)
    target_c.close()


def write_result_1(dominated_point_dict, signal_id_to_geom):
    driver = 'ESRI Shapefile'
    crs = {'init': 'epsg:32649'}
    schema = {
        'properties': OrderedDict([('id', 'int'), ('d_id', 'int'), ('dis', 'float'),]),
        'geometry': 'Point'
    }
    target_c = fiona.open('./shp/dominated_point_v3.shp', 'w', driver=driver, crs=crs, schema=schema, encoding='utf-8')
    for key, val in dominated_point_dict.items():
        dominator_key = val['dominator']
        distance = val['distance']
        rec = {
            'type': 'Feature',
            'id': '-1',
            'geometry': signal_id_to_geom[key],
            'properties': OrderedDict([('id', key), ('d_id', dominator_key), ('dis', distance)])
        }
        target_c.write(rec)
    target_c.close()


def set_out_pnt(signal_out_pnts_dict, signal, out_signal_dict, signal_list, dominated_point_dict, select_signal_out_pnt_dict):
    '''
    重新设置候选点
    '''
    well = False
    for out_pnt in signal_out_pnts_dict[signal]:
        pnt_id = out_pnt['pnt_id']                                    
        if (pnt_id not in out_signal_dict) and (pnt_id not in signal_list) and (pnt_id not in dominated_point_dict):
            out_signal_dict[pnt_id] = signal
            select_signal_out_pnt_dict[signal] = out_pnt
            well = True
            break

    if not well:                
        select_signal_out_pnt_dict[signal] = {
            'distance': 999999999999,
            'pnt_id': -1
        }
    



def main():


    SIGNAL_DISTANCE = 600
    SEARCH_DISTANCE = 3000
    

    signal_list = get_signal_list() # 得到信号灯列表
    road_graph = get_road_graph() # 得到路网

    dominated_point_dict = {} # 记录每个被统治节点的信息： 统治节点，距离统治节点的距离

    signal_out_pnts_dict = defaultdict(list) # 记录source可用的out pnts

    out_signal_dict = {} # 记录out pnt被谁使用了

    select_signal_out_pnt_dict = {} # 记录signal实际使用的out


    for signal in signal_list:
        dists = nx.single_source_dijkstra_path_length(road_graph, signal, cutoff=SEARCH_DISTANCE, weight='weight')
        out_pnts = []
        for target, distance in dists.items():
            
            if distance <= SIGNAL_DISTANCE:

                if target not in dominated_point_dict:
                    dominated_point_dict[target] = {
                        'distance': distance,
                        'dominator': signal
                    }
                else:
                    if distance < dominated_point_dict[target]['distance']:
                        dominated_point_dict[target]['distance'] = distance
                        dominated_point_dict[target]['dominator'] = signal
                    else:
                        pass

            else:
                out_pnts.append({
                    'pnt_id': target,
                    'distance': distance
                })
        assert(len(out_pnts) > 0)
        signal_out_pnts_dict[signal] = sorted(out_pnts, key=itemgetter('distance')) 


    for signal in signal_list:
        set_out_pnt(signal_out_pnts_dict, signal, out_signal_dict, signal_list, dominated_point_dict, select_signal_out_pnt_dict)
    while True:
        
        print('num of dominated pnt {}'.format(len(dominated_point_dict)))
        print('num of signal {}'.format(len(signal_list)))
        
        # 获得距离最近的候选点
        min_signal, min_out_pnt = get_min_out(select_signal_out_pnt_dict)

        if min_signal is None:
            break
        # if len(dominated_point_dict) > 10000:
        #     break
        

        new_signal = min_out_pnt['pnt_id']
        print(min_out_pnt['distance'])
        print('----')
        assert(new_signal not in signal_list)
        
        if new_signal in dominated_point_dict:
            set_out_pnt(signal_out_pnts_dict, min_signal, out_signal_dict, signal_list, dominated_point_dict, select_signal_out_pnt_dict)
            continue

        
        dists = nx.single_source_dijkstra_path_length(road_graph, new_signal, cutoff=SEARCH_DISTANCE, weight='weight')
        out_pnts = []
        for target, distance in dists.items():
            
            
            if distance <= SIGNAL_DISTANCE:

                if target not in dominated_point_dict:
                    dominated_point_dict[target] = {
                        'distance': distance,
                        'dominator': new_signal
                    }
                else:
                    if distance < dominated_point_dict[target]['distance']:
                        dominated_point_dict[target]['distance'] = distance
                        dominated_point_dict[target]['dominator'] = new_signal
                    else:
                        pass

            else:
                out_pnts.append({
                    'pnt_id': target,
                    'distance': distance
                })
        assert(len(out_pnts) > 0)
        signal_out_pnts_dict[new_signal] = sorted(out_pnts, key=itemgetter('distance')) 

        # 确定new_signal的out pnt
        signal_list.append(new_signal)
        del out_signal_dict[new_signal]

        
        set_out_pnt(signal_out_pnts_dict, new_signal, out_signal_dict, signal_list, dominated_point_dict, select_signal_out_pnt_dict)

        # 更新min_signal的out pnt
        set_out_pnt(signal_out_pnts_dict, min_signal, out_signal_dict, signal_list, dominated_point_dict, select_signal_out_pnt_dict)



    signal_id_to_geom = get_pnt_geom()
    write_result(signal_list, signal_id_to_geom)
    write_result_1(dominated_point_dict, signal_id_to_geom)
    # plt.show()

    
    


if __name__ == '__main__':
    main()
