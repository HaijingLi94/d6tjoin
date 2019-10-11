from collections import OrderedDict
import itertools, warnings

import pandas as pd
pd.set_option('display.expand_frame_repr', False)
import numpy as np

# ******************************************
# join base class
# ******************************************

class BaseJoin(object):

    def __init__(self, dfs, keys=None, keys_bydf=True, print_only=True):

        # inputs dfs
        self._init_dfs(dfs)

        if keys is not None:
            self.set_keys(keys, keys_bydf)
        else:
            self.keys = None

        self.print_only = print_only

    def _init_dfs(self, dfs):
        # check and save dfs
        if len(dfs)<2:
            raise ValueError('Need to pass at least 2 dataframes')

        if len(dfs)>2:
            raise NotImplementedError('Only handles 2 dataframes for now')

        self.dfs = dfs
        self.cfg_ndfs = len(dfs)

    def set_keys(self, keys, keys_bydf=True):
        # check and save join keys
        self._check_keys(keys)
        keys, keysdf = self._prep_keys(keys, keys_bydf)
        self._check_keysdfs(keys, keysdf)
        # join keys
        self.cfg_njoins = len(keysdf[0])
        self.keys = keys  # keys by join level
        self.keysall = keys + [['__all__'] * len(self.dfs)]
        self.keysdf = keysdf  # keys by df
        self.keysdfall = keysdf + [['__all__']] * len(self.dfs)
        self.uniques = []  # set of unique values for each join key individually
        self.keysets = []  # set of unique values for all join keys together __all__
        return keys, keysdf

    def _check_keys(self, keys):
        if not keys or len(keys)<1:
            raise ValueError("Need to have join keys")
        # todo: no duplicate join keys passed

    def _check_keysdfs(self, keys, keysdf):
        if not all([len(k)==len(self.dfs) for k in keys]):
            raise ValueError("Need to provide join keys for all dataframes")

        for idf,dfg in enumerate(self.dfs):
            dfg.head(1)[keysdf[idf]] # check that keys present in dataframe

    def _prep_keys(self, keys, keys_bydf):
        # deal with empty keys
        if not keys:
            return [], []

        # get keys in correct format given user input
        if isinstance(keys[0], (str,)):
            keysdf = [keys]*len(self.dfs)
            keys = list(map(list, zip(*keysdf)))

        elif isinstance(keys[0], (list,)):
            keysdf = list(map(list, zip(*keys)))

            if keys_bydf:
                keys, keysdf = keysdf, keys
                pass

        else:
            raise ValueError("keys need to be either list of strings or list of lists")

        return keys, keysdf

    def _return(self, result):
        if self.print_only:
            print(result)
        else:
            return result

    def _returndict(self, result):
        if self.print_only:
            for idx,d in result.items():
                print(f'dataframe #{idx}')
                print(d)
        else:
            return result


# ******************************************
# prejoin stats class
# ******************************************

class PreJoin(BaseJoin):
    """
    Analyze, slice & dice join keys and dataframes before joining. Useful for checking how good a join will be and quickly looking at unmatched join keys.

    Args:
        dfs (list): list of data frames to join
        keys (var): either list of strings `['a','b']` if join keys have the same names in all dataframes or list of lists if join keys are different across dataframes `[['a1','b1'],['a2','b2']]`
    """

    def _calc_keysets(self):

        self.keysets = [] # reset

        # find set of unique values for each join key
        for idx, dfg in enumerate(self.dfs):

            # keys individually
            uniquedict = OrderedDict()
            for key in self.keysdf[idx]:
                v = dfg[key].unique()
                uniquedict[key] = set(v[~pd.isnull(v)])

            # keys _all__
            dft = dfg[self.keysdf[idx]].drop_duplicates()
            uniquedict['__all__'] = {tuple(x) for x in dft.values}
            self.uniques.append(uniquedict)

        # perform set logic
        for keys in self.keysall:
            df_key = {}
            df_key['key left'] = keys[0]
            df_key['key right'] = keys[1]
            df_key['keyset left'] = self.uniques[0][df_key['key left']]
            df_key['keyset right'] = self.uniques[1][df_key['key right']]

            df_key['inner'] = df_key['keyset left'].intersection(df_key['keyset right'])
            df_key['outer'] = df_key['keyset left'].union(df_key['keyset right'])
            df_key['unmatched total'] = df_key['keyset left'].symmetric_difference(df_key['keyset right'])
            df_key['unmatched left'] = df_key['keyset left'].difference(df_key['keyset right'])
            df_key['unmatched right'] = df_key['keyset right'].difference(df_key['keyset left'])

            # check types are consistent
            vl = next(iter(df_key['keyset left'])) # take first element
            vr = next(iter(df_key['keyset right'])) # take first element

            df_key['value type'] = type(vl)

            self.keysets.append(df_key)

    def head(self, nrows=None, keys_only=True):
        """
        .head() of input dataframes

        Args:
            keys_only (bool): only print join keys
            nrows (int): number of rows to show
            print (bool): print or return df

        """
        nrows = self.cfg_show_nrows if nrows is None else nrows

        dfh = []
        for idf,dfg in enumerate(self.dfs):

            df = dfg

            if keys_only:
                df = dfg[self.keysdf[idf]]

            if nrows>0:
                df = df.head(nrows)

            dfh.append(df)

        result = {idx: dfg.head(nrows) for idx, dfg in enumerate(dfh)}
        self._returndict(result)

    def columns_common(self):
        result = list(set(self.dfs[0].columns.tolist()).intersection(*[dfg.columns.tolist() for dfg in self.dfs[1:]]))
        self._return(result)

    def columns_union(self):
        result = list(set().intersection(*[dfg.columns.tolist() for dfg in self.dfs]))
        self._return(result)

    def columns_ispresent(self, as_bool=False):
        # todo: maintain column order of first dataframe => take from d6tstack
        col_union = list(set().union(*[dfg.columns.tolist() for dfg in self.dfs]))
        dfr = dict(zip(range(self.cfg_ndfs),[dfg.columns.isin(col_union) for dfg in self.dfs]))
        dfr = pd.DataFrame(dfr,index=col_union).sort_index()
        if not as_bool:
            dfr = dfr.replace([True,False],['+','-'])
        self._return(dfr)

    def str_describe(self, columns=None, unique_count=False):
        """
        Returns statistics on length of all strings and other objects in pandas dataframe. Statistics include mean, median, min, max. Optional unique count.

        Args:
            dfg (dataframe): pandas dataframe
            columns (:obj:`list`, optional): column names to analyze. If None analyze all
            unique_count (:obj:`bool`, optional): include count of unique values

        Returns:
            dataframe: string length statistics
        """
        def _apply_strlen(dfg, unique_count=False):
            lenv = np.vectorize(len)
            alens = lenv(dfg.values)
            r = {'median':np.median(alens),'mean':np.mean(alens),'min':np.min(alens),'max':np.max(alens),'nrecords':dfg.shape[0]}
            if unique_count:
                r['uniques'] = len(dfg.unique())
            return pd.Series(r)

        result = {}
        for idx, dfg in enumerate(self.dfs):
            if not columns:
                columns_sel=dfg.columns
            if unique_count:
                cfg_col_sel = ['median','min','max','nrecords','uniques']
            else:
                cfg_col_sel = ['median','min','max','nrecords']
            dfo = dfg[columns_sel].select_dtypes(include=['object']).apply(lambda x: _apply_strlen(x.dropna(), unique_count)).T[cfg_col_sel]
            result[idx] = dfo
        return self._returndict(result)

    def data_describe(self, columns=None, ignore_value_columns=False):
        result = {}
        for idx, dfg in enumerate(self.dfs):

            if columns is None:
                columns_sel = dfg.columns
            else:
                if ignore_value_columns:
                    columns_sel = dfg.select_dtypes(include=['object']).columns
                else:
                    columns_sel = dfg.columns

            dfg = dfg[columns_sel]
            nunique = dfg.apply(lambda x: x.dropna().unique().shape[0]).rename('unique')
            nrecords = dfg.apply(lambda x: x.dropna().shape[0]).rename('nrecords')
            nnan = dfg.isna().sum().rename('nan')
            dfr = pd.concat([nrecords,nunique,nnan],1)
            dfr['unique rate'] = dfr['unique']/dfr['nrecords']
            result[idx] = dfr

        return self._returndict(result)

    def data_match(self, how=None, columns=None, topn=1, ignore_value_columns=True, max_unique_pct=0.8, min_unique_count=1, min_match_rate=0.5):
        '''
        todo:
            order matters, sequential inner or left joins (no right or outer joins)
            jaccard 1:2 => intersection for inner, same set for left
            
        '''
        how = 'inner' if how is None else how

        if self.cfg_ndfs >2:
            warnings.warn('Upgrade to PRO version to join >2 dataframes')

        from d6tjoin.utils import _filter_group_min

        df_left = self.dfs[0] if columns is None else self.dfs[0][columns]
        df_right = self.dfs[1] if columns is None else self.dfs[1][columns]

        def unique_dict(dfg):
            d = dict(zip(dfg.columns, [set(dfg[x].dropna().unique()) for x in dfg.columns]))
            d = {k: v for k, v in d.items() if (len(v) > min_unique_count) and (len(v)/dfg[k].shape[0] < max_unique_pct)}
            return d

        # todo: add len(key) and sample=next(key)
        values_left = unique_dict(df_left)
        values_right = unique_dict(df_right)

        df_candidates = list(itertools.product(values_left.keys(), values_right.keys()))
        df_candidates = pd.DataFrame(df_candidates, columns=['__left__', '__right__'])

        def jaccard_similarity(s1, s2, how):
            intersection = len(s1.intersection(s2))
            if how=='left':
                ratio = float(intersection / len(s1))
            else:
                union = (len(s1) + len(s2)) - intersection
                ratio = float(intersection / union)
            return ratio

        def jaccard_caller(col_left, col_right):
            return jaccard_similarity(values_left[col_left], values_right[col_right], how)

        df_candidates['__similarity__'] = df_candidates.apply(lambda x: jaccard_caller(x['__left__'], x['__right__']), axis=1)
        df_candidates = df_candidates.dropna(subset=['__similarity__'])
        if df_candidates.empty:
            raise ValueError('Failed to compute meaningful similarity, might need to loosen parameters')
        df_candidates['__similarity__'] = -df_candidates['__similarity__']
        df_diff = df_candidates.groupby('__left__',group_keys=False).apply(lambda x: _filter_group_min(x,'__similarity__',topn)).reset_index(drop=True)
        df_diff['__similarity__'] = -df_diff['__similarity__']

        df_diff['__left-sample__'] = df_diff['__left__'].map(lambda x: next(iter(values_left[x]),None))
        df_diff['__right-sample__'] = df_diff['__right__'].map(lambda x: next(iter(values_right[x]),None))
        df_diff['__left-nunique__'] = df_diff['__left__'].map(lambda x: len(values_left[x]))
        df_diff['__right-nunique__'] = df_diff['__right__'].map(lambda x: len(values_right[x]))

        if min_match_rate is not None:
            df_diff = df_diff[df_diff['__similarity__']>min_match_rate]

        # todo: sort by left df columns and then by similarity descending

        return self._return(df_diff)

    def data_similarity(self, how=None, columns=None):
        # goal: which columns data is most "similar"
        # todo: run similarity function show median/min/max similarity across columns
        # similarity on all vs all values?
        # find the top1/n similarity for each value. median across all values
        # above is strings. for numbers and dates:
        # numbers: "same distribution" => distribution similarity
        # dates: "same distribution" => distribution similarity
        # distribution similarity: non-parametric. interquartile range similar
        # want to find join keys not join value columns
        #

        raise NotImplementedError()


    def match_quality(self, rerun=False):
        """
        Show prejoin statistics

        Args:
            return_results (bool): Return results as df instead of printing

        """

        if not self.keysets or rerun:
            self._calc_keysets()

        df_out = []

        for key_set in self.keysets:
            df_key = {}
            for k in ['keyset left','keyset right','inner','outer','unmatched total','unmatched left','unmatched right']:
                df_key[k] = len(key_set[k])
            for k in ['key left','key right']:
                df_key[k] = key_set[k]
            df_key['all matched'] = df_key['inner']==df_key['outer']
            df_out.append(df_key)

        df_out = pd.DataFrame(df_out)
        df_out = df_out.rename(columns={'keyset left':'left','keyset right':'right'})
        df_out = df_out[['key left','key right','all matched','inner','left','right','outer','unmatched total','unmatched left','unmatched right']]

        self._return(df_out)

    def is_all_matched(self, key='__all__',rerun=False):

        if not self.keysets or rerun:
            self._calc_keysets()

        keymask = [key in e for e in self.keysall]
        if not (any(keymask)):
            raise ValueError('key ', self.cfg_show_key, ' not a join key in ', self.keys)
        ilevel = keymask.index(True)

        return (self.keysets[ilevel]['key left']==key or self.keysets[ilevel]['key right']==key) and len(self.keysets[ilevel]['unmatched total'])==0

    def _show_prep_df(self, idf, mode):
        """
        PRIVATE. prepare data for self.show() functions

        Args:
            idf (int): which df in self.dfs
            mode (str): matched vs unmatched

        """

        if idf==0:
            side='left'
        elif idf==1:
            side='right'
        else:
            raise ValueError('invalid idx')

        if self.cfg_show_keys_only:
            if self.cfg_show_key == '__all__':
                cfg_col_sel = self.keysdf[idf]
            else:
                cfg_col_sel = self.cfg_show_key
        else:
            cfg_col_sel = self.dfs[idf].columns

        # which set to return?
        if mode=='matched':
            cfg_mode_sel = 'inner'
        elif mode=='unmatched':
            cfg_mode_sel = mode + ' ' + side
        else:
            raise ValueError('invalid mode', mode)

        keys = list(self.keysets[self.cfg_show_level][cfg_mode_sel])
        if self.cfg_show_nrecords > 0:
            keys = keys[:self.cfg_show_nrecords]

        if self.cfg_show_key == '__all__' and self.cfg_njoins>1:
            dfg = self.dfs[idf].copy()
            dfg = self.dfs[idf].reset_index().set_index(self.keysdf[idf])
            dfg = dfg.loc[keys]
            dfg = dfg.reset_index().sort_values('index')[cfg_col_sel].reset_index(drop=True) # reorder to original order
        elif self.cfg_show_key == '__all__' and self.cfg_njoins==1:
            dfg = self.dfs[idf]
            dfg = dfg.loc[dfg[self.keysdf[idf][0]].isin([e[0] for e in keys]), cfg_col_sel]
        else:
            dfg = self.dfs[idf]
            dfg = dfg.loc[dfg[self.cfg_show_key].isin(keys),cfg_col_sel]

        if self.cfg_show_nrows > 0:
            dfg = dfg.head(self.cfg_show_nrows)

        if self.cfg_show_print_only:
            print('%s %s for key %s' %(mode, side, self.cfg_show_key))
            print(dfg)
        else:
            self.df_show_out[side] = dfg.copy()

    def _show(self, mode):
        if not self.keysets:
            raise RuntimeError('run .stats_prejoin() first')

        keymask = [self.cfg_show_key in e for e in self.keysall]
        if not (any(keymask)):
            raise ValueError('key ', self.cfg_show_key, ' not a join key in ', self.keys)
        self.cfg_show_level = keymask.index(True)

        for idf in range(self.cfg_ndfs):  # run for all self.dfs
            if self.keysall[self.cfg_show_level][idf] == self.cfg_show_key:  # check if key applies
                self._show_prep_df(idf, mode)

    def show_unmatched(self, key, nrecords=3, nrows=3, keys_only=False, print_only=False):
        """
        Show unmatched records

        Args:
            key (str): join key
            nrecords (int): number of unmatched records
            nrows (int): number of rows
            keys_only (bool): show only join keys
            print_only (bool): if false return results instead of printing
        """
        self.df_show_out = {}
        self.cfg_show_key = key
        self.cfg_show_nrecords = nrecords
        self.cfg_show_nrows = nrows
        self.cfg_show_keys_only = keys_only
        self.cfg_show_print_only = print_only

        self._show('unmatched')
        if not self.cfg_show_print_only:
            return self.df_show_out

    def show_matched(self, key, nrecords=3, nrows=3, keys_only=False, print_only=False):
        """
        Show matched records

        Args:
            key (str): join key
            nrecords (int): number of unmatched records
            nrows (int): number of rows
            keys_only (bool): show only join keys
            print_only (bool): if false return results instead of printing
        """
        self.df_show_out = {}
        self.cfg_show_key = key
        self.cfg_show_nrecords = nrecords
        self.cfg_show_nrows = nrows
        self.cfg_show_keys_only = keys_only
        self.cfg_show_print_only = print_only

        self._show('matched')
        if not self.cfg_show_print_only:
            return self.df_show_out
