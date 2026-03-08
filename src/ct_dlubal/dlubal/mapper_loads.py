class LoadMapper:
    """Standard Lastfälle für Dlubal"""
    def __init__(self, Loc):
        self.Loc = Loc

    def default_load_case(self):
        sas1 = self.Loc.StaticAnalysisSettings(no=1, name="Linear Analysis", analysis_type=0)
        lc1 = self.Loc.LoadCase(
            no=1, 
            name="Self-Weight", 
            action_category=11, 
            analysis_type=1,
            self_weight_active=True,
            self_weight_factor_z=1.0,
            static_analysis_settings=1
        )
        return [sas1, lc1]
